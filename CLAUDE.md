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
  regenerates `mavat_review.html`; log `status_diff_last.log`).
- **`MavatDiscovery`** — daily 07:30 (changed from weekly Sunday 2026-07-14):
  `mavat_scraper\run_discovery.bat` (new-plan sweep since last run → auto-rules →
  `mavat_review.html`; log `discovery_last.log`).
- **`CommitteeSweep`** — daily 08:00: `committee_scraper\run_committee_sweep.bat`
  (10 least-recently-scraped Complot **and Bartech** municipalities via
  `local_committee_scrapers` → import + Mavat-graduation dedup → regenerate
  `mavat_review.html`; log `committee_sweep_last.log`). See `docs/MAVAT_AUTOMATION.md`
  for the full design.
- **Single daily review page (2026-07-15, replaces the old two-page split)**:
  `mavat_review.html` now carries three row kinds in one place —
  **candidates** (new plans, kept/exclude), **vault-notices** (a plan already in your
  vault just showed up on the Mavat sweep for the first time — one-click dismiss,
  never repeats), and **status-changes** (a vault-tracked plan reached a tracked status —
  approve writes the new status line into the vault + units, reject just dismisses).
  Only 9 Mavat statuses are tracked at all (everything else is invisible, never written to
  the vault): `הכנת הודעה 77/78`, `הכנת תכנית`, `Pre-Ruling`, `תסקיר סביבתי`,
  `בבדיקת תנאי סף`, `בבדיקה תכנונית`, `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה` — kept in
  sync across `mavat_discover.py:TARGET_STATUSES`, `mavat_diff.py:MAVAT_TRACKED_STATUSES`,
  and `make_review_page.py:MAVAT_TRACKED_STATUSES`. Both committee-side statuses
  (`בתכנון`, `בהפקדה`) are always tracked, no filtering. Human loop: review
  `mavat_review.html` → export decisions JSON → `apply_review.py` (routes by id shape:
  bare plan = mavat candidate/vault-notice, `muni::plan` = committee, `chg::id` = status
  change) → enter **kept** candidate plans in the vault by hand (next 06:00 rebuild picks
  them up); approved **status-changes** write to the vault immediately and
  `apply_review.py` reruns `refresh_db.py` itself. The old `mavat_changes.html` /
  `make_changes_page.py` / `apply_changes.py` are retired — fully merged into the above.

## Related Scheduled Tasks (other projects)
- `Daily Projects Report Download` — Madlan back-office CSV export; had been broken
  since 2025-12; **disabled by user 2026-07-13**.
- `Municipal Plans Weekly Update` (`local_committee_scrapers`) — **disabled 2026-07-13**,
  superseded by this project's `CommitteeSweep` rotation (see above). Root cause of its
  2026-06-24 Complot outage: `ConnectionResetError 10054` — rate-limiting/anti-scraping
  by the shared `handasi.complot.co.il` backend under a full-133-municipality weekly
  burst, not a permanent block (host tested healthy 2026-07-13). Spreading the load
  daily is the actual fix, not just a schedule preference.
- `local_committee_scrapers`' Bartech plans scraper was **broken** (Selenium +
  ChromeDriver fell out of version-sync with an auto-updating system Chrome) —
  **fixed 2026-07-13**. The HTTP-rewrite lead from `C:\R_PROJECTS\Project_update_scraper`
  (whose Bartech *permits* scraper works via plain `requests`, no CAPTCHA enforced)
  turned out not to apply to plans: a live test confirmed Bartech's plans search
  (`CityPlanSearchResult`) genuinely enforces a real invisible reCAPTCHA server-side,
  rejecting a dummy token — dead end for a pure-HTTP rewrite. What worked instead:
  rewriting `systems/bartech/plans.py` to drive **Playwright** rather than Selenium.
  Plain headless Playwright passes that same invisible reCAPTCHA on its own (verified
  against Holon, full run end-to-end) — the real problem was never Bartech blocking
  bots, it was `chromedriver.exe` needing separate version-pinning against Chrome,
  which Playwright's bundled/self-managed Chromium doesn't need. `CommitteeSweep` now
  runs both systems (`--systems complot,bartech`, the default). See
  `docs/MAVAT_AUTOMATION.md` for detail.

## Session History

- **2026-07-22 — R6 regional-council blocklist, energy-rule fix**
  - Reviewed `docs/mavat_review_decisions (6).json` (11,905 decisions) specifically to
    look for new/modified auto-exclusion rules. Found a very clean pattern: 18 regional
    councils (מועצות אזוריות — rural kibbutz/moshav committees) have a **0% keep rate
    across their entire history** (thousands of exclusions each, e.g. lev hagalil 2,525,
    mateh yehuda 1,591). Added `BLOCKED_COMMITTEE_MUNIS` — an unconditional auto-exclusion
    in `auto_rules.py` (R6, committee-only). Deliberately **no content override**: testing
    showed 331 already-excluded plans in these same councils already contained a nominal
    "positive signal" keyword (שכונ/תוספת יח"ד/מתחם, which usually means "add a 3rd unit
    to one farm plot" or "internal industrial zone" in this context, not real development)
    and were rejected anyway — an override would have silently reopened all of them.
    `mitar` (Meitar) was checked individually and **excluded from the blocklist**: it
    covers real Bedouin towns (Hura) with genuine open neighborhood candidates
    (`652-0754705`, "חורה - שכונה 27"), unlike the other 18 which are purely agricultural.
    Applied once: 1,464 committee candidates excluded.
  - **`ENERGY_RULE` regex broadened** (`פוטו.?וולט` → `(פוטו|אגרו).?וולט`) to also catch
    `אגרו וולטאי` (agro-voltaic) — found on `206-1183003`, manually rejected with the
    comment "not interested in photo voltaic fields" despite being an energy plan.
  - **Process note**: per standing feedback, presented both findings (with per-municipality
    evidence, not just aggregate counts) and got explicit confirmation before touching
    `auto_rules.py` — the user's first answer ("ask me per-muni first") caught the `mitar`
    exception that a blanket "yes" would have missed.

- **2026-07-19/21 — 106(ב) detection, sanity backstop, R3/name-rule fixes, repo-hygiene pass**
  - **Section 106(ב) re-deposit detection** (`mavat_diff.py`, 2026-07-19): Mavat's status
    bucket shows the same generic `הפקדה להתנגדויות/השגות` label for an original deposit
    and a re-deposit of corrections under section 106(ב); `find_status_detail()` reads the
    plan's own stage-history log to surface the more specific label when one exists (found
    on `503-1487552`). New `mavat_changes.status_detail` column, threaded through
    `make_review_page.py`/`apply_review.py`.
  - **Silent-empty-vault sanity backstop** (`mavat_diff.py:main()`, 2026-07-19):
    `load_tracked_plans()` returning <1000 plans now hard-fails instead of silently
    running against a mid-rebuild/truncated `projects.db` — root-caused a real missed
    status change (`414-1294818`) to exactly this failure mode.
  - **`docs/TRAINEE_GUIDE.md`** added (2026-07-19): top-to-bottom onboarding explainer.
  - **R3 (units<10 auto-exclusion) now requires a CONFIRMED real unit count**
    (`auto_rules.py`, 2026-07-21): was firing on the meaningless default `units_ge10=0`
    placeholder before `mavat_discover_units.py` ever fetched a real count for the plan —
    root-caused on `416-1448794` (real units=15, wrongly excluded day one). An unconfirmed
    low count now leaves the plan open instead of guessing.
  - **`בית פרטי (צמוד קרקע)` name-rule broadened** (`auto_rules.py`, 2026-07-21): "צמוד
    קרקע" alone is now a strong enough signal without a family-type qualifier (found on
    `422-0907329`); the existing `POSITIVE_SIGNAL` override still protects genuine
    multi-unit/neighborhood plans.
  - **Stale browser-cache bug fixed** (`make_review_page.py`, 2026-07-21): a plan
    un-excluded server-side (rule fix/backlog reopen) stayed "excluded" forever in an
    already-open browser tab, since `localStorage` only ever seeded a decision once — found
    on `502-1406529`. Now only `אוטומטי:`-tagged decisions re-sync from the DB on every
    load; genuine human decisions are never touched.
  - **Repo-hygiene pass (2026-07-21)**: discovered the repo had **zero commits since
    2026-07-13** despite five sessions of real work (07-14, 07-15/16, 07-19, this one), and
    that `next_steps.md`/`CLAUDE.md` history had drifted to only cover through 07-16.
    Wrote a retroactive `SESSION_HANDOFF_2026_07_19_A.md`, removed a stray malformed output
    file (`mavat_scraper/..mavat_report.md`), backfilled `BUG_REFERENCE.md`/`VERSION_LOG.md`
    for the above, and committed everything accumulated since 07-13 — **excluding**
    `docs/rural-planning_index1.xls`/`docs/קובץ יישובים.xlsx` (superseded rural-classifier
    exploration from 2026-07-15/16, per that session's decision — left untracked, not
    deleted). **Going forward: commit at the end of each session**, don't let work
    accumulate silently.

- **2026-07-15/16 — Single-page review architecture, real unit/description detection, two data bugs fixed**
  - **Unified 9-status whitelist**: one status set (`הכנת הודעה 77/78`, `הכנת תכנית`,
    `Pre-Ruling`, `תסקיר סביבתי`, `בבדיקת תנאי סף`, `בבדיקה תכנונית`,
    `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה`) now governs new-candidate discovery,
    vault-notices, and status-change tracking together — previously three separate,
    drifting lists. Widening it retroactively flooded both the candidate queue (~14.5k
    historical `אישור`/`נדחתה` rows) and, less obviously, the vault-notice queue (1,613
    historical in-vault plans) — both bulk-dismissed per user decision (only rows
    first_seen before the cutover), so only genuinely new plans surface going forward.
    **Explicitly reverted**: an attempt to also auto-exclude 77/78-status plans — a batch
    of stale rejections at that status looked like a pattern, but the user wants to keep
    seeing *new* 77/78 candidates as an early planning-intent signal.
  - **`mavat_review.html` merged into one page**: added `vault_notice` (a vault-tracked
    plan's first Mavat appearance, one-click dismiss — Mavat's own page is often richer
    than the committee source the plan was entered from) and `status_change` (absorbs the
    retired `mavat_changes.html`, keyed `chg::<id>`) row kinds. `make_changes_page.py`,
    `apply_changes.py`, `mavat_changes.html` deleted; logic merged into
    `make_review_page.py`/`apply_review.py`.
  - **Real per-plan unit counts + description-text interpretation**
    (`mavat_discover_units.py`, new file): the `--tag-units` sweep was a stale one-off
    snapshot from 2026-07-12 — confirmed a real bug on `302-1493931` (tagged <10 units,
    actually 300 real units). Same fetch also reads the plan's free-text description
    (`recExplanation.EXPLANATION`) and un-excludes an R3-excluded candidate when the text
    signals a sizeable project despite no parseable unit count (user-approved keyword list
    + >10-dunam land-area check) — confirmed on `259-1374917` ("רובע מגורים ותעסוקה...
    106 ד'"). Runs ongoing (no backlog catch-up, per user) as a daily `run_discovery.bat`
    step.
  - **Two real bugs found and fixed**: a SQL `NOT LIKE` filter against a nullable column
    silently hid every open candidate for a day (NULL-handling — any `NOT LIKE`/`!=`
    filter on a nullable column needs an explicit `IS NULL OR` guard); `status_date`/
    `decision_date` were swapped in the Mavat field mapping (`BI_STATUS_DATE` is the date
    shown next to a plan's current status; `INTERNET_STATUS_DATE` tracks the latest entry
    across the whole stage-history table and can advance on unrelated administrative
    sub-steps) — backfilled `mavat_state.db` for free, dismissed 4 false-positive pending
    status changes this bug had caused.
  - **`RefreshProjectsDB` fixed**: was calling bare `python` (PATH lookup, had started
    failing with `ERROR_FILE_NOT_FOUND`) instead of a full interpreter path.
  - Applied a 2,959-decision review batch (2,885 excluded, 60 kept, 7 vault-notices
    dismissed, 3 status-changes approved). Full detail in
    `docs/session_handoffs/SESSION_HANDOFF_2026_07_16_A.md`.

- **2026-07-14 — Bartech fix, dedup gap, MavatDiscovery daily, review cleanup**
  - **Bartech plans fixed**: rewrote `local_committee_scrapers`'
    `systems/bartech/plans.py` from Selenium to Playwright. Root cause was never Bartech
    blocking bots — Selenium's ChromeDriver needs separate version-pinning against an
    auto-updating system Chrome, and it fell behind. The HTTP-rewrite lead (from
    `Project_update_scraper`'s Bartech *permits* scraper, which works via plain `requests`
    since Bartech's permit-search CAPTCHA isn't server-enforced) turned out not to apply to
    plans — a live test confirmed the plans search enforces a real invisible reCAPTCHA
    server-side. Plain headless Playwright passes that challenge on its own; no solver
    needed. `CommitteeSweep` now runs `--systems complot,bartech` (verified live: Holon,
    497 plans).
  - **`MavatDiscovery` moved to daily 07:30** (was weekly Sunday) at user request.
  - **Mavat-graduation dedup gap fixed**: the committee/Mavat dedup only checked the
    committee scraper's own קישור למבאת column + the vault, never `mavat_discovery.db`'s
    own plan list — found via a concrete duplicate (Ashdod 603-1218759). Added
    `reconcile_with_mavat_discovery()`, backfilled 35 affected rows.
  - **`auto_rules.py` extended to committee candidates** (previously mavat-only): new R4
    (non-local/national plan-number format, 83% of the open committee queue) + R5
    (test/placeholder rows). Open committee queue: 205 → 0.
  - **Export-button Hebrew corruption root-caused and fixed**: missing UTF-8 BOM/charset
    on the download `Blob` in both `mavat_review.html` and `mavat_changes.html`; added BOM
    + `apply_review.py`/`apply_changes.py` now read `utf-8-sig`. Verified end-to-end via a
    Playwright click-through test.
  - Applied 15 pending Mavat status-change decisions (7 approved, 7 rejected, 1 already
    applied) and a batch of 22 kept-plan review decisions (3 entered into the vault).
  - Fixed a one-off vault content corruption (AZUR שלב א' קפלן 3 ו-5) — a pasted URL with
    embedded newlines had been parsed into bogus `- צפי::` bullets; merged back, URL
    dropped per user's call.
  - Decided (not tasks): keep the `·משוער` marker; `project_type` classification is not
    worth further investment (zero downstream consumers).
  - Deleted obsolete one-off logs in `mavat_scraper\`.

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
