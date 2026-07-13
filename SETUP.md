# Setup Guide

Quick start for the Projects Vault → DB pipeline and the Mavat status scraper.

**Last Updated:** 2026-07-08

---

## Prerequisites

- **Windows 10/11** (this is a Windows project; PowerShell examples below).
- **Python 3.13+** — interpreters live at
  `C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe` (and `Python314`).
  Note: `python` is not reliably on PATH in interactive shells; call the full path, or use the
  scraper venv below.
- **Obsidian vault** present at:
  `C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה\לוז פרויקטים\לוז פרויקטים\שכונות`

Always run Python with UTF-8 for Hebrew output: `python -X utf8 ...` or set `$env:PYTHONUTF8=1`.

---

## Part 1 — Vault → DB pipeline

Core files in `scripts/` (the scheduled task uses absolute paths — update it if you move them):
`scripts/refresh_db.py` (pipeline), `scripts/build_db.py` (core logic), `scripts/structure_vault.py`
(one-time migration). Outputs (`projects.db`/`.csv`/`.xlsx`) live at repo root.

### Run manually
```powershell
$py = "C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe"
$vault = "C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה\לוז פרויקטים\לוז פרויקטים\שכונות"
& $py -X utf8 "C:\R_PROJECTS\projects_monitor\scripts\refresh_db.py" $vault "C:\R_PROJECTS\projects_monitor\projects.db"
```

### Scheduled automation
- Task Scheduler: **`RefreshProjectsDB`** — daily 06:00, runs the command above from working
  directory `C:\R_PROJECTS\projects_monitor`.
- Inspect / change:
  ```powershell
  Get-ScheduledTask -TaskName RefreshProjectsDB | Select-Object -ExpandProperty Actions
  # Set-ScheduledTask / Unregister-ScheduledTask to modify or remove
  ```
- Related tasks to review: `Daily Projects Report Download`, `Municipal Plans Weekly Update`.

---

## Part 2 — Mavat status scraper (`mavat_scraper/`)

Has its **own venv** (Python 3.13 + Playwright + Chromium) so it doesn't touch the pipeline env.

### First-time setup (already done on this machine)
```powershell
$py = "C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe"
& $py -m venv "C:\R_PROJECTS\projects_monitor\mavat_scraper\venv"
$vpy = "C:\R_PROJECTS\projects_monitor\mavat_scraper\venv\Scripts\python.exe"
& $vpy -m pip install playwright
& $vpy -m playwright install chromium
```

### Run a lookup
```powershell
$env:PYTHONUTF8=1
$vpy = "C:\R_PROJECTS\projects_monitor\mavat_scraper\venv\Scripts\python.exe"

# One or more plan numbers (headless, warm session):
& $vpy "C:\R_PROJECTS\projects_monitor\mavat_scraper\mavat_status.py" --headless 457-1253954 457-1260348

# From a file, write JSON:
& $vpy "C:\R_PROJECTS\projects_monitor\mavat_scraper\mavat_status.py" --headless --file plans.txt --json out.json
```

Flags: `--headless` (unattended), `--cold` (fresh context per plan; benchmarking), `--no-block`
(don't block images/fonts), `--file <path>`, `--json <path>`.

Output per plan: `plan, matched, mid, name, location, authority, status_desc, status_short,
status_code, status_date, decision_date, update_date, url`.

See [docs/MAVAT_AUTOMATION.md](docs/MAVAT_AUTOMATION.md) for the design, WAF findings, and the
current verdict.

---

## Verifying things work
- Pipeline: after a run, `projects.db` mod-time updates; `projects` table has ~10,507 rows.
- Scraper: `... mavat_status.py --headless 457-1253954` should print
  `[OK ] 457-1253954  אישור  code=4480 ...`.

## Troubleshooting
- **Hebrew crashes the console** (`UnicodeEncodeError: cp1252`): add `-X utf8` / `$env:PYTHONUTF8=1`.
- **Scraper misses every plan under concurrency**: known — see `conc_test.py` notes in
  `next_steps.md`; run serially/low-concurrency for now.
- **Scheduled task fails**: confirm `python` resolves in the task's run context and the vault
  Dropbox path is synced/available.
