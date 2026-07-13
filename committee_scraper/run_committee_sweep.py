r"""
run_committee_sweep.py — daily rotation over local-planning-committee scrapers
(C:\R_PROJECTS\local_committee_scrapers), spread across many days instead of one
weekly burst against a shared backend (root cause of the 2026-06-24 Complot outage:
all 70 Complot municipalities proxy through one host, handasi.complot.co.il, which
rate-limited/reset connections under a full-133 weekly blast).

This project's own code is NOT duplicated here — we invoke the other project's venv
+ its `run_subset.py` entry point (added 2026-07-13, additive, does not touch its
existing scripts) for N least-recently-scraped municipalities, then import the
resulting per-municipality master-table CSVs into committee_state.db.

Dedup with Mavat (user decision 2026-07-13): the committee CSVs carry a קישור למבאת
(Mavat link) column. A committee-discovered plan whose link is populated has already
entered the Mavat pipeline and does not need separate committee-level tracking —
workflow is local-committee preapproval -> Mavat process -> Mavat approval. Such rows
are auto-"graduated" (excluded, reason recorded, link kept for reference) rather than
surfaced as open candidates. A secondary check cross-references the plan number
against the vault (`projects.db`) for the same reason.

Usage (run with projects_monitor's own interpreter — no extra deps needed):
  python run_committee_sweep.py --count 20                 # 20 least-recently-scraped
  python run_committee_sweep.py --munis haifa ashdod        # explicit subset
  python run_committee_sweep.py --count 20 --systems complot,bartech
"""
import argparse
import csv
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
STATE_DB = HERE / "committee_state.db"
PROJECTS_DB = HERE.parent / "projects.db"

SCRAPER_ROOT = Path(r"C:\R_PROJECTS\local_committee_scrapers\unified_scraper\municipal_scraper")
SCRAPER_PY = SCRAPER_ROOT / ".venv" / "Scripts" / "python.exe"

MAVAT_LINK_PLAN_RX = re.compile(r"[?&]text=([0-9]{3}-[0-9]{6,8})")


def open_state():
    con = sqlite3.connect(STATE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS committee_muni_state(
        muni TEXT PRIMARY KEY, system TEXT, last_scraped_at TEXT, last_result TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS committee_candidates(
        id TEXT PRIMARY KEY, muni TEXT, plan_number TEXT, plan_name TEXT,
        status TEXT, status_date TEXT, plan_type TEXT, authority TEXT, developer TEXT,
        mavat_link TEXT, mavat_plan_number TEXT, plan_link TEXT,
        first_seen TEXT, last_seen TEXT,
        graduated INTEGER DEFAULT 0, graduated_at TEXT,
        excluded INTEGER DEFAULT 0, exclude_reason TEXT, comment TEXT,
        kept INTEGER DEFAULT 0, decided_at TEXT)""")
    con.commit()
    return con


def get_registry():
    """Fetch MUNI_REGISTRY from the other project's own venv — never duplicated/hardcoded
    here, so it can't drift out of sync with that project's own municipality list."""
    code = ("import json; from registry.dispatcher import MUNI_REGISTRY; "
            "print(json.dumps(MUNI_REGISTRY))")
    r = subprocess.run([str(SCRAPER_PY), "-c", code], cwd=str(SCRAPER_ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"could not read MUNI_REGISTRY: {r.stderr[-500:]}")
    return json.loads(r.stdout)


def pick_rotation(state, registry, count, systems):
    cur = state.execute("SELECT muni, last_scraped_at FROM committee_muni_state")
    last = dict(cur.fetchall())
    candidates = [m for m, cfg in registry.items() if cfg.get("system") in systems]
    ordered = sorted(candidates, key=lambda m: (last.get(m) or "", m))
    return ordered[:count]


def run_subset(munis):
    """Invoke the scraper project's own venv for this municipality subset."""
    cmd = [str(SCRAPER_PY), "run_subset.py"] + munis
    print(f"[..] invoking scraper for {len(munis)} municipalities: {', '.join(munis)}",
          flush=True)
    r = subprocess.run(cmd, cwd=str(SCRAPER_ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if line.startswith(("[", "done:")):
            print("   ", line, flush=True)
    if r.returncode != 0:
        print("   [!] subset run exited non-zero:", (r.stderr or "")[-500:], flush=True)
    return r


def vault_plan_numbers():
    con = sqlite3.connect(PROJECTS_DB)
    nums = {str(r[0]).strip().replace(" ", "")
           for r in con.execute("SELECT plan_current FROM projects WHERE plan_current != ''")}
    con.close()
    return nums


def import_master_csv(state, muni, vault_plans, now):
    """Read this municipality's master CSV and reconcile against committee_candidates:
    new open candidates, status refresh, and Mavat-graduation detection."""
    slug = muni.replace(" ", "_")
    path = SCRAPER_ROOT / "output" / "plans" / "data" / slug / f"{slug}-plans-master-table.csv"
    if not path.exists():
        print(f"   [!] no master CSV for {muni} at {path}")
        return {"rows": 0, "new": 0, "graduated": 0}

    stats = {"rows": 0, "new": 0, "graduated": 0}
    cur = state.cursor()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            plan_number = (row.get("מספר תוכנית") or "").strip()
            if not plan_number:
                continue
            stats["rows"] += 1
            cid = f"{muni}::{plan_number}"
            mavat_link = (row.get("קישור למבאת") or "").strip()
            m = MAVAT_LINK_PLAN_RX.search(mavat_link)
            mavat_plan_number = m.group(1) if m else None
            plan_norm = plan_number.replace(" ", "")

            cur.execute("SELECT graduated, excluded FROM committee_candidates WHERE id=?",
                       (cid,))
            prev = cur.fetchone()

            graduate = bool(mavat_link) or (plan_norm in vault_plans)
            reason = None
            if mavat_link:
                reason = 'כבר במבא"ת (קישור זוהה)'
            elif plan_norm in vault_plans:
                reason = "כבר במעקב הכספת (vault)"

            if prev is None:
                stats["new"] += 1
                if graduate:
                    stats["graduated"] += 1
                cur.execute("""INSERT INTO committee_candidates(
                        id, muni, plan_number, plan_name, status, status_date,
                        plan_type, authority, developer, mavat_link, mavat_plan_number,
                        plan_link, first_seen, last_seen, graduated, graduated_at,
                        excluded, exclude_reason)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, muni, plan_number, row.get("שם תוכנית"), row.get("סטטוס"),
                     row.get("תאריך סטטוס"), row.get("סוג התוכנית"), row.get("בסמכות"),
                     row.get("יזם"), mavat_link or None, mavat_plan_number,
                     row.get("קישור לתוכנית"), now, now,
                     1 if graduate else 0, now if graduate else None,
                     1 if graduate else 0, reason))
            else:
                was_graduated = prev[0]
                cur.execute("""UPDATE committee_candidates SET
                        plan_name=?, status=?, status_date=?, plan_type=?, authority=?,
                        developer=?, mavat_link=?, mavat_plan_number=?, plan_link=?,
                        last_seen=?
                    WHERE id=?""",
                    (row.get("שם תוכנית"), row.get("סטטוס"), row.get("תאריך סטטוס"),
                     row.get("סוג התוכנית"), row.get("בסמכות"), row.get("יזם"),
                     mavat_link or None, mavat_plan_number, row.get("קישור לתוכנית"),
                     now, cid))
                if graduate and not was_graduated:
                    stats["graduated"] += 1
                    cur.execute("""UPDATE committee_candidates SET graduated=1,
                            graduated_at=?, excluded=1, exclude_reason=? WHERE id=?""",
                        (now, reason, cid))
    state.commit()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, help="N least-recently-scraped municipalities")
    ap.add_argument("--munis", nargs="+", help="explicit municipality list")
    ap.add_argument("--systems", default="complot",
                    help="comma-separated system types to include (default: complot only "
                        "— bartech excluded pending its ChromeDriver fix)")
    args = ap.parse_args()
    systems = set(args.systems.split(","))

    if not SCRAPER_PY.exists():
        sys.exit(f"scraper venv not found: {SCRAPER_PY}")

    state = open_state()
    registry = get_registry()

    if args.munis:
        targets = args.munis
    elif args.count:
        targets = pick_rotation(state, registry, args.count, systems)
    else:
        sys.exit("choose --count N or --munis ...")

    if not targets:
        print("[OK] nothing to scrape (no municipalities matched)")
        return

    print(f"[..] {len(targets)} municipalities this run: {', '.join(targets)}", flush=True)
    run_subset(targets)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vault_plans = vault_plan_numbers()
    total_new = total_graduated = 0
    for muni in targets:
        stats = import_master_csv(state, muni, vault_plans, now)
        state.execute("""INSERT INTO committee_muni_state(muni, system, last_scraped_at,
                             last_result)
                         VALUES(?,?,?,?)
                         ON CONFLICT(muni) DO UPDATE SET last_scraped_at=excluded.last_scraped_at,
                             last_result=excluded.last_result""",
                     (muni, registry.get(muni, {}).get("system"), now, json.dumps(stats)))
        state.commit()
        total_new += stats["new"]
        total_graduated += stats["graduated"]
        print(f"   {muni}: {stats['rows']} rows, {stats['new']} new, "
              f"{stats['graduated']} already-in-mavat", flush=True)

    cur = state.execute("""SELECT COUNT(*) FROM committee_candidates
                           WHERE excluded=0 AND COALESCE(kept,0)=0""")
    open_total = cur.fetchone()[0]
    print(f"\n[OK] swept {len(targets)} municipalities; {total_new} new candidates, "
          f"{total_graduated} auto-graduated (already in Mavat/vault); "
          f"{open_total} open committee candidates total")
    state.close()


if __name__ == "__main__":
    main()
