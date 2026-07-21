r"""
apply_review.py — import decisions exported from mavat_review.html back into the
correct source, routed by id shape (never ambiguous):
  - "muni::plan_number"  -> committee_scraper/committee_state.db (committee candidate)
  - "chg::<id>"          -> mavat_state.db mavat_changes (status-change approval; approving
                            writes a new status line into the vault, same as the retired
                            apply_changes.py did — merged in 2026-07-15)
  - bare plan number     -> mavat_discovery.db (candidate, or a 'seen' vault-notice)

Prints exclusion-reason stats (input for filter tuning) and the kept-plans queue (to enter
into the vault). Refreshes projects.db automatically if any status change was approved.

Usage:
  venv\Scripts\python.exe apply_review.py "%USERPROFILE%\Downloads\mavat_review_decisions.json"
  venv\Scripts\python.exe apply_review.py decisions.json --no-refresh
"""
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
MAVAT_DB = HERE / "mavat_discovery.db"
COMMITTEE_DB = HERE.parent / "committee_scraper" / "committee_state.db"
STATE_DB = HERE / "mavat_state.db"
PROJECTS_DB = HERE.parent / "projects.db"
VAULT = Path(r"C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה"
             r"\לוז פרויקטים\לוז פרויקטים\שכונות")
REFRESH = HERE.parent / "scripts" / "refresh_db.py"
SYS_PY = r"C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe"

args = [a for a in sys.argv[1:] if a != "--no-refresh"]
no_refresh = "--no-refresh" in sys.argv[1:]
if len(args) != 1:
    sys.exit("usage: apply_review.py <decisions.json> [--no-refresh]")
decisions = json.loads(Path(args[0]).read_text(encoding="utf-8-sig"))


def vault_blocks_for_plan(plan):
    """(relpath, project_name) for every project carrying this plan number."""
    con = sqlite3.connect(PROJECTS_DB)
    rows = con.execute("""SELECT DISTINCT relpath, project_name FROM projects
                          WHERE REPLACE(TRIM(plan_current),' ','')=?""", (plan,)).fetchall()
    con.close()
    return rows


def append_status(relpath, plan, status_line):
    """Append `- סטטוס:: <status_line>` inside the block anchored by `תכנית:: <plan>`.
    Returns a human-readable outcome string. (Moved from the retired apply_changes.py.)"""
    path = VAULT / relpath
    if not path.exists():
        return f"[X] vault file missing: {relpath}"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    anchor = None
    plan_rx = re.compile(r"^\s*-\s*תכנית::\s*" + re.escape(plan) + r"\s*$")
    for i, ln in enumerate(lines):
        if plan_rx.match(ln):
            anchor = i
            break
    if anchor is None:
        return f"[X] plan {plan} not found in {relpath}"

    start = 0
    for i in range(anchor, -1, -1):
        if lines[i].startswith("#### "):
            start = i
            break
    end = len(lines)
    for i in range(anchor + 1, len(lines)):
        if lines[i].startswith("#### "):
            end = i
            break

    status_idxs = [i for i in range(start, end)
                   if re.match(r"^\s*-\s*סטטוס::", lines[i])]
    new_line = f"- סטטוס:: {status_line}"
    moved_marker = False
    for i in status_idxs:
        if "(נוכחי)" in lines[i]:
            lines[i] = re.sub(r"\s*\(נוכחי\)\s*$", "", lines[i])
            moved_marker = True
    if moved_marker:
        new_line += " (נוכחי)"

    insert_at = (status_idxs[-1] + 1) if status_idxs else (anchor + 1)
    if any(status_line in lines[i] for i in status_idxs):
        return f"[=] already present in {relpath}"
    lines.insert(insert_at, new_line)
    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""),
                    encoding="utf-8")
    return f"[OK] {relpath}: + {new_line}"

mavat_con = sqlite3.connect(MAVAT_DB)
for ddl in ("ALTER TABLE discovered ADD COLUMN kept INTEGER DEFAULT 0",
            "ALTER TABLE discovered ADD COLUMN decided_at TEXT",
            "ALTER TABLE discovered ADD COLUMN vault_notice_seen INTEGER DEFAULT 0",
            "ALTER TABLE discovered ADD COLUMN vault_notice_seen_at TEXT"):
    try:
        mavat_con.execute(ddl)
    except sqlite3.OperationalError:
        pass

committee_con = sqlite3.connect(COMMITTEE_DB) if COMMITTEE_DB.exists() else None
state_con = sqlite3.connect(STATE_DB) if STATE_DB.exists() else None

n_ex = n_keep = n_open = n_seen = n_mavat = n_committee = 0
n_chg_approved = n_chg_rejected = 0
kept_rows = []   # (source, plan_display, name, location, status, comment)
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for d in decisions:
    state = d.get("state")
    plan_key = d["plan"]

    # "chg::<id>" = a status-change approval/rejection (mavat_state.db:mavat_changes),
    # merged in from the retired mavat_changes.html/apply_changes.py (2026-07-15). Checked
    # BEFORE the committee "::" check since this id shape also contains "::".
    if plan_key.startswith("chg::"):
        if not state_con:
            print(f"[?] {plan_key}: mavat_state.db not found — skipped")
            continue
        chg_id = int(plan_key.split("::", 1)[1])
        row = state_con.execute(
            """SELECT plan, new_status, new_date, note, status_detail FROM mavat_changes
               WHERE id=? AND approved IS NULL""", (chg_id,)).fetchone()
        if not row:
            print(f"[?] change id {chg_id} not pending — skipped")
            continue
        plan, new_status, new_date, note, status_detail = row
        if state == "rejected":
            state_con.execute("UPDATE mavat_changes SET approved=0, note=? WHERE id=?",
                              (d.get("comment") or note, chg_id))
            n_chg_rejected += 1
        elif state == "approved":
            if note == "units-only" or not new_status:
                state_con.execute("""UPDATE mavat_changes SET approved=1, applied_at=?
                                     WHERE id=?""", (now, chg_id))
                n_chg_approved += 1
                print(f"[OK] {plan}: units change acknowledged (no vault line)")
            else:
                # status_detail (2026-07-19): the plan's own stage-history label for this
                # date when it names a section-106(ב) re-deposit-after-corrections — write
                # that instead of Mavat's generic status bucket, matching how this would be
                # entered manually (distinguishing an original deposit from a 106(ב) redo).
                status_line = f"{status_detail or new_status} {new_date}".strip()
                targets = vault_blocks_for_plan(plan)
                if not targets:
                    print(f"[X] {plan}: no vault project found — left pending")
                    continue
                ok_any = False
                for relpath, _name in targets:
                    outcome = append_status(relpath, plan, status_line)
                    print(f"  {plan}: {outcome}")
                    ok_any = ok_any or outcome.startswith(("[OK]", "[="))
                if ok_any:
                    state_con.execute("""UPDATE mavat_changes SET approved=1, applied_at=?,
                                         note=? WHERE id=?""",
                                      (now, d.get("comment") or note, chg_id))
                    n_chg_approved += 1
        continue

    is_committee = "::" in plan_key

    # "seen" = a vault-notice dismissal (plan already tracked in the vault, just showed up
    # in the Mavat sweep) — never a committee-side state, and must not touch excluded/kept.
    if state == "seen" and not is_committee:
        n_mavat += 1
        n_seen += 1
        mavat_con.execute("""UPDATE discovered SET vault_notice_seen=1,
                                 vault_notice_seen_at=COALESCE(?, vault_notice_seen_at)
                             WHERE plan=?""", (d.get("ts") or None, plan_key))
        continue

    excluded = 1 if state == "excluded" else 0
    kept = 1 if state == "kept" else 0

    if is_committee:
        if not committee_con:
            print(f"[?] {d['plan']}: committee_state.db not found — skipped")
            continue
        n_committee += 1
        committee_con.execute("""UPDATE committee_candidates SET excluded=?, kept=?,
                                     exclude_reason=?, comment=?,
                                     decided_at=COALESCE(?, decided_at)
                                 WHERE id=?""",
                              (excluded, kept, d.get("reason") or None,
                               d.get("comment") or None, d.get("ts") or None, d["plan"]))
        cur = committee_con.execute(
            "SELECT plan_number, plan_name, muni, status FROM committee_candidates "
            "WHERE id=?", (d["plan"],))
        row = cur.fetchone()
        if kept and row:
            kept_rows.append(("ועדה מקומית", row[0], row[1], row[2], row[3],
                              d.get("comment") or ""))
    else:
        n_mavat += 1
        mavat_con.execute("""UPDATE discovered SET excluded=?, kept=?, exclude_reason=?,
                                 comment=?, decided_at=COALESCE(?, decided_at)
                             WHERE plan=?""",
                          (excluded, kept, d.get("reason") or None,
                           d.get("comment") or None, d.get("ts") or None, d["plan"]))
        cur = mavat_con.execute("SELECT name, location, status FROM discovered WHERE plan=?",
                               (d["plan"],))
        row = cur.fetchone()
        if kept and row:
            kept_rows.append(("מבא\"ת", d["plan"], row[0], row[1], row[2],
                              d.get("comment") or ""))

    if state == "excluded":
        n_ex += 1
    elif state == "kept":
        n_keep += 1
    else:
        n_open += 1

mavat_con.commit()
if committee_con:
    committee_con.commit()
if state_con:
    state_con.commit()

print(f"[OK] applied {len(decisions)} decisions ({n_mavat} mavat, {n_committee} committee): "
      f"{n_ex} excluded, {n_keep} kept, {n_seen} vault-notices seen, "
      f"{n_open} reverted-to-open, {n_chg_approved} status-changes approved, "
      f"{n_chg_rejected} status-changes rejected")

print("\n== exclusion reasons (filter-tuning input) ==")
print("-- mavat --")
for reason, n in mavat_con.execute("""SELECT COALESCE(exclude_reason,'(no reason)'), COUNT(*)
                                      FROM discovered WHERE excluded=1
                                      GROUP BY exclude_reason ORDER BY 2 DESC"""):
    print(f"  {n:4d}  {reason}")
if committee_con:
    print("-- committee --")
    for reason, n in committee_con.execute(
            """SELECT COALESCE(exclude_reason,'(no reason)'), COUNT(*)
               FROM committee_candidates WHERE excluded=1
               GROUP BY exclude_reason ORDER BY 2 DESC"""):
        print(f"  {n:4d}  {reason}")

print("\n== kept plans (to enter into the vault) ==")
for source, plan, name, loc, status, comment in kept_rows:
    print(f"  [{source}] {plan}  |  {loc or ''}  |  {name or ''}  |  {status or ''}"
          + (f"  //  {comment}" if comment else ""))

mavat_con.close()
if committee_con:
    committee_con.close()
if state_con:
    state_con.close()

if n_chg_approved and not no_refresh:
    print("\n[..] refreshing projects.db from the vault ...")
    r = subprocess.run([SYS_PY, "-X", "utf8", str(REFRESH), str(VAULT), str(PROJECTS_DB)],
                       capture_output=True, text=True, encoding="utf-8")
    tail = (r.stdout or "").strip().splitlines()[-3:]
    for ln in tail:
        print("   ", ln)
    if r.returncode != 0:
        print("[X] refresh_db failed:", (r.stderr or "").strip()[-300:])
    else:
        print("[OK] projects.db refreshed")
