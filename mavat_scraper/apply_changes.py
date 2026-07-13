r"""
apply_changes.py — apply approved Mavat status changes to the VAULT (and refresh the DB).

Takes the decisions JSON exported from mavat_changes.html. For each approved change:
  1. Finds every vault project block whose `תכנית::` equals the plan number.
  2. Appends a `- סטטוס:: <status> <date>` line after the block's last status line.
     If the block carries a `(נוכחי)` marker, the marker moves to the new line.
  3. Marks the change approved+applied in mavat_state.db (rejected ones are just marked).
Finally (unless --no-refresh) reruns scripts/refresh_db.py so projects.db reflects the
vault immediately instead of waiting for the 06:00 task.

Only explicit user approval reaches the vault — this script never invents content; the
appended line is exactly Mavat's status label + date shown on the approval page.

Usage:
  venv\Scripts\python.exe apply_changes.py "%USERPROFILE%\Downloads\mavat_changes_decisions.json"
"""
import argparse
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
STATE_DB = HERE / "mavat_state.db"
PROJECTS_DB = HERE.parent / "projects.db"
VAULT = Path(r"C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה"
             r"\לוז פרויקטים\לוז פרויקטים\שכונות")
REFRESH = HERE.parent / "scripts" / "refresh_db.py"
SYS_PY = r"C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe"


def vault_blocks_for_plan(plan):
    """(relpath, list-of-project-names) for every project carrying this plan number."""
    con = sqlite3.connect(PROJECTS_DB)
    rows = con.execute("""SELECT DISTINCT relpath, project_name FROM projects
                          WHERE REPLACE(TRIM(plan_current),' ','')=?""", (plan,)).fetchall()
    con.close()
    return rows


def append_status(relpath, plan, status_line):
    """Append `- סטטוס:: <status_line>` inside the block anchored by `תכנית:: <plan>`.
    Returns a human-readable outcome string."""
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

    # block bounds: previous '#### ' header (or start) .. next '#### ' header (or EOF)
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
    # if the block marks a current status explicitly, the marker moves to the new line
    moved_marker = False
    for i in status_idxs:
        if "(נוכחי)" in lines[i]:
            lines[i] = re.sub(r"\s*\(נוכחי\)\s*$", "", lines[i])
            moved_marker = True
    if moved_marker:
        new_line += " (נוכחי)"

    insert_at = (status_idxs[-1] + 1) if status_idxs else (anchor + 1)
    # duplicate guard: identical status line already present in the block
    if any(status_line in lines[i] for i in status_idxs):
        return f"[=] already present in {relpath}"
    lines.insert(insert_at, new_line)
    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""),
                    encoding="utf-8")
    return f"[OK] {relpath}: + {new_line}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decisions", help="mavat_changes_decisions.json from the approval page")
    ap.add_argument("--no-refresh", action="store_true",
                    help="do not rerun refresh_db.py after applying")
    args = ap.parse_args()

    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    state = sqlite3.connect(STATE_DB)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_applied = n_rejected = 0

    for d in decisions:
        cur = state.execute("""SELECT plan, new_status, new_date, note FROM mavat_changes
                               WHERE id=? AND approved IS NULL""", (d["id"],))
        row = cur.fetchone()
        if not row:
            print(f"[?] change id {d['id']} not pending — skipped")
            continue
        plan, new_status, new_date, note = row

        if d["action"] == "reject":
            state.execute("UPDATE mavat_changes SET approved=0, note=? WHERE id=?",
                          (d.get("comment") or note, d["id"]))
            n_rejected += 1
            continue
        if d["action"] != "approve":
            continue

        if note == "units-only" or not new_status:
            # nothing to write to the vault for units-only changes; just acknowledge
            state.execute("UPDATE mavat_changes SET approved=1, applied_at=? WHERE id=?",
                          (now, d["id"]))
            n_applied += 1
            print(f"[OK] {plan}: units change acknowledged (no vault line)")
            continue

        status_line = f"{new_status} {new_date}".strip()
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
            state.execute("UPDATE mavat_changes SET approved=1, applied_at=?, note=? "
                          "WHERE id=?", (now, d.get("comment") or note, d["id"]))
            n_applied += 1

    state.commit()
    state.close()
    print(f"\n[OK] applied {n_applied}, rejected {n_rejected}")

    if n_applied and not args.no_refresh:
        print("[..] refreshing projects.db from the vault ...")
        r = subprocess.run([SYS_PY, "-X", "utf8", str(REFRESH), str(VAULT),
                            str(PROJECTS_DB)], capture_output=True, text=True,
                           encoding="utf-8")
        tail = (r.stdout or "").strip().splitlines()[-3:]
        for ln in tail:
            print("   ", ln)
        if r.returncode != 0:
            print("[X] refresh_db failed:", (r.stderr or "").strip()[-300:])
        else:
            print("[OK] projects.db refreshed")


if __name__ == "__main__":
    main()
