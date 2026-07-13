# Session Handoff — 2026-07-08 A

## Status: Doc framework established; Mavat scraper prototyped (headless works)

---

## What Happened This Session

### 1. Mavat status scraper — built and benchmarked (`mavat_scraper/`)
Continuation of the 2026-07-06 source research. Goal narrowed by the user to a **quick daily
check: did a plan's status change, and when** (no committee-decision history needed).

Findings (all from real runs against the live site from an Israeli IP):
- **A browser is required** — plain HTTP stays blocked, and even an in-page
  `fetch('/rest/api/SV4/1?mid=...')` from a warmed page returns the 404 WAF page.
- **Headless Chromium passes the WAF** — no `playwright-stealth`/`patchright` needed.
  `navigator.webdriver` is `true` even headed and the site still serves data; the WAF only
  wants genuine in-browser JS execution. → runs as a clean unattended job, no display.
- **Best extraction path**: submitting a plan number triggers `POST /rest/api/sv3/Search`, whose
  result row already carries `UNIFIED_STATUS_DESC`, `INTERNET_STATUS_CODE` (stable numeric,
  great for diffing), `INTERNET_STATUS_DATE`, `BI_STATUS_DATE`, and the `mid`. No detail page.
- Verified on `457-1253954` → אישור, code 4480, decision 28/06/2026 (matches prior manual test).
- Benchmarks (headless): ~7s cold per plan, ~6s warm. Projection: ~1,000 plans ≈ 100 min
  single-threaded, ~30-35 min at concurrency 3.

Gotchas found & fixed (see `docs/BUG_REFERENCE.md`): all-plans radio, aria-label selector,
fast-miss (39s → 6s). robots.txt is permissive (only images/PDFs disallowed).

Scope decisions by the user: **old-format Hebrew plan numbers out of scope**; committee history
not needed.

### 2. Documentation framework established (this session's main deliverable)
Mirrored the `C:\R_PROJECTS\Transit_Score` layout:
- Root: `README.md`, `CLAUDE.md`, `next_steps.md`, `SETUP.md`.
- `docs/`: `DATA_FLOW.md`, `SCHEMAS.md`, `MAVAT_AUTOMATION.md` (the moved findings log),
  `BUG_REFERENCE.md`, `VERSION_LOG.md`, plus moved specs (`framework_spec.md`,
  `structure_proposal.md`, `vocab_review.md`, `HANDOFF_vault_pipeline.md`).
- `docs/session_handoffs/` (this file), `memory/MEMORY.md`, `tests/` skeleton.
- Adopted the `SESSION_HANDOFF_YYYY_MM_DD_X.md` naming convention.

### 3. Verified ground truth (not assumed)
- `projects.db` has **five tables** built by `refresh_db.py`: `projects` (~10,516),
  `status_events` (~12,026, ~92% mapped, with `is_current`), `tenders` (~2,426),
  `signatures` (~7,131), `value_history` (~2,354). An earlier "single table" note was an
  inspection bug (reused sqlite cursor) — corrected.
- `projects_from_notes.db` was proven a **strict subset** of `projects.db` (0 unique projects,
  0 differing payloads) and removed.

### 4. Housekeeping (files + task)
- Moved core pipeline to **`scripts/`** (`refresh_db.py`, `build_db.py`, `structure_vault.py`);
  outputs (`projects.db`/`.csv`/`.xlsx`) stay at root. (`parse_vault.py` never existed here.)
- Updated **`RefreshProjectsDB`** task to `scripts\refresh_db.py` (vault + output args unchanged).
  Verified the moved pipeline rebuilds all 5 tables end-to-end (to a temp DB; live `projects.db`
  left for the 06:00 run — vault has grown to ~10,516).
- Removed one-off Mavat probes; kept `mavat_status.py` and `conc_test.py`.
- The other two scheduled tasks are **separate projects** (`C:\R_PROJECTS\...`), not ours.

---

## Key Files

| File | Purpose |
|---|---|
| `mavat_scraper/mavat_status.py` | working scraper (`--headless`, `--cold`, `--file`, `--json`) |
| `mavat_scraper/conc_test.py` | concurrency test (needs a clean re-run) |
| `scripts/refresh_db.py` / `scripts/build_db.py` | vault → DB pipeline (scheduled) |
| `docs/MAVAT_AUTOMATION.md` | Mavat findings + verdict |
| `docs/SCHEMAS.md` | DB schema + 33-code vocabulary |

---

## Next Steps (see `next_steps.md`)

1. **Re-run the concurrency test** (`conc_test.py`) now that the async route handler is fixed;
   get a real read on parallel throughput and WAF/IP behavior. Add polite rate-limiting.
   (Parked by the user until housekeeping is done — housekeeping is now done.)
2. **Wire the diff**: for each `plan_current`, look up Mavat and compare vs.
   `status_events.is_current` (the target already exists). Optionally add a `mavat_seen`
   snapshot table (plan → status_code + date + fetched_at).
3. Map Mavat status codes → the 33-code `STAGE_LABEL` vocabulary in `scripts/build_db.py`.
4. New-plan discovery: first check the separate `local_committee_scrapers` /
   `projects_file_download` projects (their own scheduled tasks) before duplicating.

## Watch out for
- Run everything Python with `-X utf8` (Hebrew).
- Don't move `refresh_db.py` / `build_db.py` / `projects.db` without updating `RefreshProjectsDB`.
- Don't write derived/automation values back into the vault notes (layer separation).
