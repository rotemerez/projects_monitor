# Project Memory Index — Projects Vault → DB & Mavat Automation

One-line pointers to durable project facts. Keep entries short; details live in `docs/`.

## Configuration & Setup
- User: Rotem Erez.
- Project: tracking Israeli neighborhood construction/planning projects; vault → `projects.db`
  → daily Mavat status automation.
- Vault (source of truth):
  `C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה\לוז פרויקטים\לוז פרויקטים\שכונות`
- Repo root: `C:\R_PROJECTS\projects_monitor`. Core pipeline in `scripts/`
  (`refresh_db.py`, `build_db.py`, `structure_vault.py`); outputs (`projects.db`/`.csv`/`.xlsx`)
  at root. `RefreshProjectsDB` task uses absolute paths — keep in sync if moving files.
- Python: `...\AppData\Local\Programs\Python\Python313\python.exe` (`python` not on PATH in
  interactive shells). Scraper venv: `mavat_scraper\venv` (Playwright + Chromium).
- Always run with `-X utf8` / `$env:PYTHONUTF8=1` for Hebrew.

## Scheduled tasks
- `RefreshProjectsDB` — daily 06:00, `scripts\refresh_db.py <vault> projects.db`.
- `Daily Projects Report Download` (`C:\R_PROJECTS\projects_file_download`) and
  `Municipal Plans Weekly Update` (`C:\R_PROJECTS\local_committee_scrapers\...`) are **separate
  projects** — relevant to new-plan discovery; don't duplicate them.

## Known working states
- `projects.db` — 5 tables: `projects` (~10,516), `status_events` (~12,026, ~92% mapped,
  `is_current`), `tenders` (~2,426), `signatures` (~7,131), `value_history` (~2,354). Verified
  2026-07-08. `projects_from_notes.db` was a strict subset; removed.
- Mavat scraper — headless lookup verified on `457-1253954` → אישור, decision 28/06/2026.

## Key facts / gotchas
- Mavat: plain HTTP + in-page fetch are WAF-blocked; **headless Playwright driving the search UI
  works** (no stealth). `sv3/Search` row has status + numeric code + date — enough for daily diff.
- Mavat diff target = `status_events.is_current` (join via `plan_current`). See `docs/SCHEMAS.md`.
- sqlite gotcha: don't reuse one cursor to query inside a `sqlite_master` loop (truncates it) —
  use a second cursor / `fetchall()`.

## Session history
- 2026-07-08 — doc framework established; Mavat prototype benchmarked. See
  `docs/session_handoffs/SESSION_HANDOFF_2026_07_08_A.md`.
