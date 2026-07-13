r"""
apply_review.py — import decisions exported from mavat_review.html back into the
correct source DB (mavat_discovery.db for Mavat-sourced candidates, or
committee_scraper/committee_state.db for committee-sourced ones — routed by the id
shape: a committee id is "muni::plan_number", a Mavat id is a bare plan number/string,
so the two are never ambiguous). Prints exclusion-reason stats (input for filter
tuning) and the kept-plans queue (to enter into the vault).

Usage:
  venv\Scripts\python.exe apply_review.py "%USERPROFILE%\Downloads\mavat_review_decisions.json"
"""
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
MAVAT_DB = HERE / "mavat_discovery.db"
COMMITTEE_DB = HERE.parent / "committee_scraper" / "committee_state.db"

if len(sys.argv) != 2:
    sys.exit("usage: apply_review.py <decisions.json>")
decisions = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

mavat_con = sqlite3.connect(MAVAT_DB)
for ddl in ("ALTER TABLE discovered ADD COLUMN kept INTEGER DEFAULT 0",
            "ALTER TABLE discovered ADD COLUMN decided_at TEXT"):
    try:
        mavat_con.execute(ddl)
    except sqlite3.OperationalError:
        pass

committee_con = sqlite3.connect(COMMITTEE_DB) if COMMITTEE_DB.exists() else None

n_ex = n_keep = n_open = n_mavat = n_committee = 0
kept_rows = []   # (source, plan_display, name, location, status, comment)

for d in decisions:
    state = d.get("state")
    excluded = 1 if state == "excluded" else 0
    kept = 1 if state == "kept" else 0
    is_committee = "::" in d["plan"]

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

print(f"[OK] applied {len(decisions)} decisions ({n_mavat} mavat, {n_committee} committee): "
      f"{n_ex} excluded, {n_keep} kept, {n_open} reverted-to-open")

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
