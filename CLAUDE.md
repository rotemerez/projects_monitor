# Claude Code Session Notes — Projects Vault → DB & Mavat Automation

## Project Overview

Tracking of construction/planning projects (תכניות בנייה/התחדשות) across Israeli
neighborhoods. An Obsidian **vault** (human source of truth) is normalized into a SQLite
**database** (analysis/automation layer), and a daily **Mavat scraper** keeps each plan's
status current by querying מנהל התכנון.

- **Vault** (source of truth, in Dropbox):
  `C:\Users\Rotem\madlan Dropbox\rotem erez\מדלן תוכן\תכניות תחבורה\לוז פרויקטים\לוז פרויקטים\שכונות`
  — one Markdown file per neighborhood; one `#### <name>` block per project; Dataview inline
  fields (`שדה:: ערך`); one status event per line.
- **DB**: `projects.db` (SQLite, ~10,507 projects).
- **Automation goal**: daily diff of live Mavat status vs. stored status → alert on progress;
  plus discovery of new plans in the projects' towns.

## Current Status

- **Vault → DB pipeline**: DONE and scheduled. `refresh_db.py` reads the structured vault and
  builds `projects.db` daily (Task Scheduler `RefreshProjectsDB`, 06:00).
- **DB shape (verified 2026-07-08)**: `projects.db` contains **five tables** built by
  `scripts/refresh_db.py`: `projects` (~10,516), `status_events` (~12,026, ~92% mapped to a
  canonical stage code, with `is_current`), `tenders` (~2,426), `signatures` (~7,131),
  `value_history` (~2,354). The redundant `projects_from_notes.db` (a strict subset) was
  removed. `status_events.is_current` is the natural Mavat diff target. See `docs/SCHEMAS.md`.
- **Mavat scraper** (`mavat_scraper/`): working prototype. **Verdict: headless Playwright
  works** against the WAF; search-only extraction returns status + status code + date per plan.
  Concurrency test and polite rate-limiting still pending. See `docs/MAVAT_AUTOMATION.md`.

## Active Documentation

- **[next_steps.md](next_steps.md)** — live task tracking (update as work progresses).
- **[docs/](docs/)** — architecture, schema, Mavat findings, spec, bugs, version log.
- This file (`CLAUDE.md`) — session notes and project context.

## Session Handoff Documents

### Naming Convention
Handoff files live in `docs/session_handoffs/` and follow: `SESSION_HANDOFF_YYYY_MM_DD_X.md`
- `YYYY_MM_DD` — session date.
- `X` — ordered letter within the day: `A`, `B`, `C`, … (resets to `A` each new day).

### Rules
- **Never overwrite** an existing handoff. Each session creates a new file with the next letter.
- At the **start** of a session, read the latest handoff; if it is missing its `_X` suffix, rename it to add one.
- At the **end** of each session, create `docs/session_handoffs/SESSION_HANDOFF_YYYY_MM_DD_X.md`.

## Project Organization Standards

### Folder Structure
```
projects_monitor/
├── scripts/                 # core pipeline
│   ├── refresh_db.py        #   live pipeline: structured vault -> projects.db
│   ├── build_db.py          #   core logic (vocab, dates, tenders, numbers); imported by refresh_db
│   └── structure_vault.py   #   one-time migration that produced the structured vault
├── projects.db, projects.csv, projects.xlsx                        # outputs (root)
├── README.md, CLAUDE.md, next_steps.md, SETUP.md                    # top-level docs
├── docs/                    # all other documentation
│   └── session_handoffs/    # per-session handoff notes
├── memory/                  # project memory index (MEMORY.md) + memory files
├── mavat_scraper/           # Playwright status scraper (own venv) — mavat_status.py, conc_test.py
└── tests/                   # test scripts (skeleton)
```

### Scheduled task ↔ file paths (keep in sync)
The `RefreshProjectsDB` task invokes `scripts\refresh_db.py` and writes `projects.db` by
**absolute path** (workdir = repo root); `refresh_db.py` imports `build_db.py` from its own
directory (`scripts/`). If you move any of these, update the task in the same step
(`Set-ScheduledTask -TaskName RefreshProjectsDB`). Outputs (`projects.db`/`.csv`/`.xlsx`) live
at root because the task passes `projects.db` as its output argument.

## Development Guidelines

### Code Style
- **No fabricated data.** If a source returns nothing or a fetch fails, surface it (empty /
  error / explicit NULL) — never backfill placeholder values. (See global CLAUDE.md.)
- Clear comments for non-obvious logic; meaningful names; keep the codebase modular.
- Prefer editing existing files over adding new ones.

### Hebrew Language & Encoding
- Primary data language is **Hebrew (RTL)**. Ensure **UTF-8** everywhere.
- Python: set `PYTHONUTF8=1` (or `python -X utf8`) when running scripts that print Hebrew —
  the Windows console defaults to cp1252 and will crash on Hebrew otherwise. The scheduled task
  already uses `python -X utf8`.
- Plan numbers exist in **new format** (`457-1253954`) and **old format** (`הל/מח/567`,
  `32/03/122/12`). Old-format lookups are currently out of scope for status updates.

### Windows Console Compatibility
- Do **not** print Unicode symbols (✓, ✗, ►, ▼) in console output — use ASCII (`[OK]`, `[X]`,
  `->`). Emoji/box-drawing characters break `cp1252` consoles.

### Environment
- `python` / `python3` are **not** reliably on PATH in interactive shells; the scheduled task
  runs in a context where `python` resolves. Interpreters:
  `C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe` (and `Python314`).
- The Mavat scraper has its **own venv**: `mavat_scraper\venv\Scripts\python.exe` (Python 3.13,
  Playwright + Chromium installed).

## Model Selection (cost control)
- **Haiku** — default for routine work (edits, docs, simple fixes, file ops, searches).
- **Sonnet** — architecture, multi-file refactors, complex debugging, schema/design work.
- **Opus/Fable** — only when clearly justified.

## External Data Sources (join keys)
- **Plan number** (`projects.plan_current`) → מנהל התכנון / Mavat (status, stages, dates).
- **Tender number** (`tender_raw`, format `מחוז/מספר/שנה` e.g. `ים/212/2025`) → רמ"י.
- Early urban-renewal fields (signatures, developer selection) and forecasts are **manual** —
  no official feed.

## Scheduled Tasks (this project)
- **`RefreshProjectsDB`** — daily 06:00: vault → `projects.db`.
- **`MavatStatusDiff`** — daily 07:00: `mavat_scraper\run_status_diff.bat`
  (300-plan status rotation, `--details 25` units baseline; changes → `mavat_report.md`;
  approval page → `mavat_changes.html`; log `status_diff_last.log`).
- **`MavatDiscovery`** — weekly Sunday 07:30: `mavat_scraper\run_discovery.bat`
  (new-plan sweep since last run → auto-rules → `mavat_review.html`;
  log `discovery_last.log`).
- **`CommitteeSweep`** — daily 08:00: `committee_scraper\run_committee_sweep.bat`
  (10 least-recently-scraped Complot municipalities via `local_committee_scrapers` →
  import + Mavat-graduation dedup → regenerate `mavat_review.html`;
  log `committee_sweep_last.log`). See `docs/MAVAT_AUTOMATION.md` for the full design.
- Human loop (both discovery sources, one page): review `mavat_review.html` → export
  decisions JSON → `apply_review.py` (routes by source) → enter **kept** plans in the
  vault by hand → next 06:00 rebuild picks them up as tracked.
  Status changes: `mavat_changes.html` → export → `apply_changes.py` (writes approved
  changes to the vault + reruns `refresh_db.py`).

## Related Scheduled Tasks (other projects)
- `Daily Projects Report Download` — Madlan back-office CSV export; had been broken
  since 2025-12; **disabled by user 2026-07-13**.
- `Municipal Plans Weekly Update` (`local_committee_scrapers`) — **disabled 2026-07-13**,
  superseded by this project's `CommitteeSweep` rotation (see above). Root cause of its
  2026-06-24 Complot outage: `ConnectionResetError 10054` — rate-limiting/anti-scraping
  by the shared `handasi.complot.co.il` backend under a full-133-municipality weekly
  burst, not a permanent block (host tested healthy 2026-07-13). Spreading the load
  daily is the actual fix, not just a schedule preference.
- `local_committee_scrapers`' Bartech plans scraper (Selenium) is **currently broken**
  independent of the above — Chrome auto-updated past the pinned ChromeDriver version.
  Excluded from `CommitteeSweep` (Complot only) pending a fix. A promising alternative
  surfaced from `C:\R_PROJECTS\Project_update_scraper` (a newer, unrelated project):
  its Bartech *permit* scraper found the CAPTCHA on Bartech sites isn't server-enforced
  (a dummy `g-recaptcha-response` value works) and scrapes via plain `requests`, no
  browser. The *plans* endpoint (`SearchCityPlan`) does fire real XHR/POST requests
  (confirmed via a Playwright network capture 2026-07-13) — plausible the same gap
  exists there, which would mean rewriting Bartech-plans as pure HTTP rather than
  patching ChromeDriver. Not pursued further this session — deferred, not fixed.

## Session History

- **2026-07-06 → 2026-07-08 — Mavat automation research + prototype**
  - Confirmed plain HTTP (and even in-page `fetch`) is blocked by the gov.il WAF; **headless
    Playwright driving the search UI works**. No stealth needed.
  - Best path: the `sv3/Search` result row already carries current status + numeric status
    code + status date — enough for the daily "did it change, and when" check; no detail page.
  - Built `mavat_scraper/mavat_status.py` (warm session, asset-blocking, fast-miss). Benchmarks:
    ~7s cold / ~6s warm per plan headless. Verified against `457-1253954` (אישור, 28/06/2026).
  - Established this documentation framework (mirrors the Transit_Score project layout).
  - **Housekeeping (2026-07-08)**: moved core pipeline to `scripts/` and updated the
    `RefreshProjectsDB` task; verified the moved pipeline rebuilds all 5 tables end-to-end;
    confirmed `projects_from_notes.db` was a strict subset and removed it; cleaned the one-off
    Mavat probes (kept `mavat_status.py`, `conc_test.py`).
  - **Open**: concurrency test + polite rate-limiting, then wire the daily diff against
    `status_events.is_current` (the diff target already exists in the DB).
