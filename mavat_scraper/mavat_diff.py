r"""
mavat_diff.py — daily Mavat status diff for the plans tracked in projects.db.

For each new-format plan number (NNN-NNNNNNN) in projects.plan_current, look up the live
Mavat status (headless Playwright, via MavatSession in mavat_status.py) and compare it to
the previous snapshot. Emits a change report and updates the snapshot.

State lives in mavat_scraper/mavat_state.db (NOT in projects.db, which is rebuilt daily
by the RefreshProjectsDB task and would wipe any extra table):
  mavat_status  — latest snapshot per plan (one row per plan)
  mavat_changes — append-only log of observed changes

Change signal (per docs/MAVAT_AUTOMATION.md): status label + status date are primary;
status_code alone is NOT treated as a change (observed to shift while the label stayed).

Usage (run with mavat_scraper venv):
  venv\Scripts\python.exe mavat_diff.py --rotate 300          # 300 least-recently-checked
  venv\Scripts\python.exe mavat_diff.py --plans 457-1253954   # explicit plans
  venv\Scripts\python.exe mavat_diff.py --all                 # full sweep (hours)
  add --report out.md to write the change report to a file
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from mavat_status import MavatSession

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
PROJECTS_DB = HERE.parent / "projects.db"
STATE_DB = HERE / "mavat_state.db"
NEW_FORMAT = re.compile(r"^\d{3}-\d{6,8}$")

DELAY_S = 2.0            # polite inter-request delay
RETRY_BACKOFF_S = 5.0    # wait before re-querying a MISS once
SESSION_RECYCLE = 250    # restart the browser context every N lookups

# Terminal statuses — once a plan reaches one there is nothing to monitor on Mavat, so it
# goes dormant and drops out of rotation (--include-dormant overrides).
# אישור = approved; נדחתה = rejected (added per user decision 2026-07-08).
TERMINAL_MAVAT_STATUSES = {"אישור", "נדחתה"}
TERMINAL_VAULT_STAGES = {"approved"}

# Transitions the user does not track manually in the vault, so they must not surface as
# reportable changes either (user decision 2026-07-13). The snapshot is still updated
# silently — so a later move e.g. בהליך אישור -> אישור is still correctly detected as a
# change against the last REPORTED status, not against this suppressed intermediate one.
IGNORED_NEW_STATUSES = {"בהליך אישור"}


def load_tracked_plans():
    """Distinct new-format plans + vault context (name/city/current vault stage)."""
    con = sqlite3.connect(PROJECTS_DB)
    cur = con.cursor()
    cur.execute("""
        SELECT p.plan_current, p.city, p.project_name, e.stage_code, e.stage_label, e.date_norm
        FROM projects p
        LEFT JOIN status_events e ON e.project_id = p.project_id AND e.is_current = 1
        WHERE p.plan_current LIKE '%-%'
    """)
    plans = {}
    for plan, city, name, stage_code, stage, date in cur.fetchall():
        plan = str(plan).strip().replace(" ", "")
        if not NEW_FORMAT.match(plan):
            continue
        # several projects can share a plan; keep the first context row
        plans.setdefault(plan, {"city": city, "name": name, "vault_stage_code": stage_code,
                                "vault_stage": stage, "vault_date": date})
    con.close()
    return plans


def parse_quantities(detail):
    """Extract (residential_units_total, quantities_list) from an SV4 detail JSON.
    Values arrive as strings like '+2,423'; units total = authorised + added for the
    'מגורים (יח"ד)' quantity row (code 120)."""
    def num(v):
        try:
            return int(str(v).replace(",", "").replace("+", "").strip())
        except (ValueError, TypeError):
            return 0

    rows = (detail or {}).get("rsQuantities") or []
    quantities = []
    units = None
    for q in rows:
        item = {"code": q.get("QUANTITY_CODE"), "desc": q.get("QUANTITY_DESC"),
                "unit": q.get("UNIT_DESC"),
                "authorised": num(q.get("AUTHORISED_QUANTITY")),
                "added": num(q.get("AUTHORISED_QUANTITY_ADD"))}
        item["total"] = item["authorised"] + item["added"]
        quantities.append(item)
        if 'יח"ד' in str(q.get("QUANTITY_DESC") or "") or q.get("QUANTITY_CODE") == 120.0:
            units = item["total"]
    return units, quantities


def open_state():
    con = sqlite3.connect(STATE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS mavat_status(
        plan TEXT PRIMARY KEY, matched INTEGER,
        status_desc TEXT, status_code INTEGER, status_date TEXT,
        decision_date TEXT, update_date TEXT, mid INTEGER, name TEXT,
        first_seen TEXT, last_checked TEXT, last_changed TEXT,
        dormant INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS mavat_changes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan TEXT, changed_at TEXT,
        old_status TEXT, old_date TEXT, new_status TEXT, new_date TEXT, note TEXT)""")
    for ddl in ("ALTER TABLE mavat_status ADD COLUMN dormant INTEGER DEFAULT 0",
                "ALTER TABLE mavat_status ADD COLUMN units INTEGER",
                "ALTER TABLE mavat_status ADD COLUMN quantities TEXT",
                "ALTER TABLE mavat_status ADD COLUMN details_at TEXT",
                "ALTER TABLE mavat_changes ADD COLUMN old_units INTEGER",
                "ALTER TABLE mavat_changes ADD COLUMN new_units INTEGER",
                "ALTER TABLE mavat_changes ADD COLUMN approved INTEGER",
                "ALTER TABLE mavat_changes ADD COLUMN applied_at TEXT"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    # terminal statuses recorded before the flag existed
    qmarks = ",".join("?" * len(TERMINAL_MAVAT_STATUSES))
    con.execute(f"UPDATE mavat_status SET dormant=1 "
                f"WHERE dormant=0 AND status_desc IN ({qmarks})",
                tuple(TERMINAL_MAVAT_STATUSES))
    con.commit()
    return con


def select_active(state, plans, include_dormant=False):
    """Plans that still need monitoring: not Mavat-terminal (dormant flag) and not already
    approved in the vault. include_dormant=True returns everything."""
    if include_dormant:
        return set(plans)
    cur = state.cursor()
    cur.execute("SELECT plan FROM mavat_status WHERE dormant=1")
    dormant = {r[0] for r in cur.fetchall()}
    return {p for p, ctx in plans.items()
            if p not in dormant and ctx.get("vault_stage_code") not in TERMINAL_VAULT_STAGES}


def pick_rotation(state, active, n):
    """N active plans, least-recently-checked first (never-checked plans first)."""
    cur = state.cursor()
    cur.execute("SELECT plan, last_checked FROM mavat_status")
    checked = dict(cur.fetchall())
    ordered = sorted(active, key=lambda p: (checked.get(p) or "", p))
    return ordered[:n]


def lookup_iter(target_plans, headless=True):
    """Warm-session lookups with polite delay, retry-once-on-miss, session recycling.
    Yields one result at a time so the caller can persist incrementally — a long run
    that dies mid-way keeps everything already checked. A crash inside one lookup
    (e.g. goto timeout when the site stalls) must not kill the whole run: it is
    retried once in a fresh session, then reported as an error result."""
    with sync_playwright() as p:
        session = None

        def fresh():
            nonlocal session
            if session:
                session.close()
            session = MavatSession(p, headless=headless)

        def fetch_detail(mid):
            """Detail fetch using the current session; crash-safe (returns None)."""
            try:
                return session.fetch_detail(mid)
            except Exception:
                fresh()
                return None

        fresh()
        try:
            for i, plan in enumerate(target_plans):
                if i and i % SESSION_RECYCLE == 0:
                    fresh()
                if i:
                    time.sleep(DELAY_S)
                try:
                    r = session.lookup(plan)
                except Exception as e:
                    r = {"plan": plan, "matched": False,
                         "error": f"lookup_crash:{type(e).__name__}"}
                if not r.get("matched"):
                    # retry in a FRESH session: an observed flaky miss failed the
                    # same-session retry but matched in a new one; a crashed session
                    # must be replaced anyway
                    fresh()
                    time.sleep(RETRY_BACKOFF_S)
                    try:
                        r = session.lookup(plan)
                    except Exception as e:
                        r = {"plan": plan, "matched": False,
                             "error": f"lookup_crash:{type(e).__name__}"}
                        fresh()
                    r["retried"] = True
                yield r, fetch_detail
        finally:
            if session:
                session.close()


def store_details(state, plan, detail, now):
    """Parse + persist a detail fetch; returns (old_units, new_units)."""
    cur = state.cursor()
    cur.execute("SELECT units FROM mavat_status WHERE plan=?", (plan,))
    row = cur.fetchone()
    old_units = row[0] if row else None
    units, quantities = parse_quantities(detail)
    cur.execute("""UPDATE mavat_status SET units=?, quantities=?, details_at=?
                   WHERE plan=?""",
                (units, json.dumps(quantities, ensure_ascii=False), now, plan))
    return old_units, units


def diff_and_store(state, results, plans, fetcher=None):
    """Compare each result to the stored snapshot; log + return changes. When a change
    is detected and fetcher is given, the plan's SV4 details are fetched to capture
    unit-count changes alongside the status change."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = state.cursor()
    changes, new_plans, misses, errors = [], [], [], []
    for r in results:
        plan = r["plan"]
        if r.get("error"):
            # lookup failure (e.g. filter not settable) — NOT a miss; leave state untouched
            # so the rotation re-picks the plan next run
            errors.append(plan)
            continue
        cur.execute("SELECT status_desc, status_date, matched FROM mavat_status WHERE plan=?",
                    (plan,))
        prev = cur.fetchone()
        if not r.get("matched"):
            misses.append(plan)
            if prev:
                cur.execute("UPDATE mavat_status SET last_checked=? WHERE plan=?", (now, plan))
            else:
                cur.execute("""INSERT INTO mavat_status(plan, matched, first_seen, last_checked)
                               VALUES(?,0,?,?)""", (plan, now, now))
            continue
        dormant = 1 if r.get("status_desc") in TERMINAL_MAVAT_STATUSES else 0
        if prev is None or not prev[2]:
            new_plans.append(r)
            cur.execute("""INSERT INTO mavat_status(plan, matched, status_desc, status_code,
                               status_date, decision_date, update_date, mid, name,
                               first_seen, last_checked, last_changed, dormant)
                           VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(plan) DO UPDATE SET matched=1,
                               status_desc=excluded.status_desc, status_code=excluded.status_code,
                               status_date=excluded.status_date, decision_date=excluded.decision_date,
                               update_date=excluded.update_date, mid=excluded.mid,
                               name=excluded.name, last_checked=excluded.last_checked,
                               last_changed=excluded.last_changed, dormant=excluded.dormant""",
                        (plan, r.get("status_desc"), r.get("status_code"), r.get("status_date"),
                         r.get("decision_date"), r.get("update_date"), r.get("mid"),
                         r.get("name"), now, now, now, dormant))
            continue
        old_status, old_date = prev[0], prev[1]
        changed = (r.get("status_desc") != old_status) or (r.get("status_date") != old_date)
        # ignored transitions still update the snapshot (below) so a LATER real move is
        # diffed against the true last status, not this suppressed intermediate one —
        # but they never become a change record the user has to review
        if changed and r.get("status_desc") in IGNORED_NEW_STATUSES:
            changed = False
        if changed:
            old_units = new_units = None
            if fetcher and r.get("mid"):
                detail = fetcher(r["mid"])
                if detail:
                    old_units, new_units = store_details(state, plan, detail, now)
            changes.append({"plan": plan, "old_status": old_status, "old_date": old_date,
                            "new_status": r.get("status_desc"), "new_date": r.get("status_date"),
                            "old_units": old_units, "new_units": new_units,
                            "ctx": plans.get(plan, {})})
            cur.execute("""INSERT INTO mavat_changes(plan, changed_at, old_status, old_date,
                               new_status, new_date, old_units, new_units)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (plan, now, old_status, old_date,
                         r.get("status_desc"), r.get("status_date"), old_units, new_units))
        cur.execute("""UPDATE mavat_status SET matched=1, status_desc=?, status_code=?,
                           status_date=?, decision_date=?, update_date=?, mid=?, name=?,
                           last_checked=?, last_changed=COALESCE(?, last_changed), dormant=?
                       WHERE plan=?""",
                    (r.get("status_desc"), r.get("status_code"), r.get("status_date"),
                     r.get("decision_date"), r.get("update_date"), r.get("mid"), r.get("name"),
                     now, now if changed else None, dormant, plan))
    state.commit()
    return changes, new_plans, misses, errors


def write_report(path, changes, new_plans, misses, plans, checked_n, elapsed_s):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Mavat status report — {today}", "",
             f"Checked {checked_n} plans in {round(elapsed_s / 60, 1)} min. "
             f"**{len(changes)} changes**, {len(new_plans)} first-time snapshots, "
             f"{len(misses)} misses.", ""]
    if changes:
        lines.append("## Status changes")
        lines.append("")
        lines.append("| plan | project | old | new | new date | units |")
        lines.append("|---|---|---|---|---|---|")
        for ch in changes:
            ctx = ch["ctx"]
            proj = f"{ctx.get('city') or ''} / {ctx.get('name') or ''}".strip(" /")
            ou, nu = ch.get("old_units"), ch.get("new_units")
            units = (f"{ou} → **{nu}**" if ou is not None and nu is not None and ou != nu
                     else (str(nu) if nu is not None else ""))
            lines.append(f"| {ch['plan']} | {proj} | {ch['old_status']} ({ch['old_date']}) "
                         f"| **{ch['new_status']}** | {ch['new_date']} | {units} |")
        lines.append("")
        lines.append("לאישור/דחייה של עדכונים אל הכספת: `mavat_changes.html` (נוצר בכל ריצה).")
        lines.append("")
    if misses:
        lines.append("## Misses (not found on Mavat, after one retry)")
        lines.append("")
        for m in misses:
            ctx = plans.get(m, {})
            lines.append(f"- {m} — {ctx.get('city') or ''} / {ctx.get('name') or ''}")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", help="comma-separated explicit plan numbers")
    ap.add_argument("--rotate", type=int, help="check the N least-recently-checked plans")
    ap.add_argument("--all", action="store_true", help="full sweep of every active plan")
    ap.add_argument("--include-dormant", action="store_true",
                    help="also check approved/terminal plans (normally skipped)")
    ap.add_argument("--details", type=int, default=0, metavar="N",
                    help="also fetch SV4 details (units) for N plans lacking a units "
                         "baseline (changed plans always get a detail fetch)")
    ap.add_argument("--report", help="write a Markdown change report to this path")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    plans = load_tracked_plans()
    state = open_state()
    active = select_active(state, plans, include_dormant=args.include_dormant)

    if args.plans:
        targets = [p.strip() for p in args.plans.split(",") if p.strip()]
    elif args.all:
        targets = sorted(active)
    elif args.rotate:
        targets = pick_rotation(state, active, args.rotate)
    else:
        ap.error("choose one of --plans / --rotate N / --all")

    print(f"[..] {len(targets)} plans to check "
          f"({len(plans)} tracked, {len(plans) - len(active)} dormant/approved skipped)",
          flush=True)
    t0 = time.time()
    changes, new_plans, misses, errors = [], [], [], []
    hits = 0
    for i, (r, fetcher) in enumerate(lookup_iter(targets, headless=not args.headed)):
        c, n, m, e = diff_and_store(state, [r], plans, fetcher=fetcher)
        changes += c
        new_plans += n
        misses += m
        errors += e
        hits += 1 if r.get("matched") else 0
        done = i + 1
        if done % 25 == 0 or done == len(targets):
            print(f"  ... {done}/{len(targets)} looked up ({hits} matched)", flush=True)

        # units baseline: piggyback a few detail fetches per run on the same session
        if args.details and done == len(targets):
            cur = state.execute("""SELECT plan, mid FROM mavat_status
                                   WHERE matched=1 AND dormant=0 AND mid IS NOT NULL
                                     AND details_at IS NULL LIMIT ?""", (args.details,))
            todo = cur.fetchall()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fetched = 0
            units_changes = 0
            for plan_d, mid in todo:
                time.sleep(DELAY_S)
                detail = fetcher(mid)
                if not detail:
                    continue
                old_u, new_u = store_details(state, plan_d, detail, now)
                state.commit()
                fetched += 1
                if old_u is not None and new_u is not None and old_u != new_u:
                    units_changes += 1
                    state.execute("""INSERT INTO mavat_changes(plan, changed_at,
                                       old_status, old_date, new_status, new_date,
                                       old_units, new_units, note)
                                     VALUES(?,?,NULL,NULL,NULL,NULL,?,?,'units-only')""",
                                  (plan_d, now, old_u, new_u))
                    state.commit()
            if todo:
                print(f"  ... details fetched for {fetched}/{len(todo)} plans "
                      f"({units_changes} unit changes)", flush=True)
    elapsed = time.time() - t0

    print(f"\n[OK] checked={len(targets)} changes={len(changes)} new={len(new_plans)} "
          f"misses={len(misses)} errors={len(errors)} in {round(elapsed / 60, 1)} min")
    for ch in changes:
        print(f"  CHANGE {ch['plan']}: {ch['old_status']} ({ch['old_date']}) -> "
              f"{ch['new_status']} ({ch['new_date']})")
    if args.report:
        write_report(args.report, changes, new_plans, misses, plans, len(targets), elapsed)
        print("wrote", args.report)
    state.close()


if __name__ == "__main__":
    main()
