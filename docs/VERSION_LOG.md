# Version Log

**Last Updated:** 2026-07-21

Release / change history, newest on top.

---

## 2026-07-19/21 — 106(ב) detection, sanity backstop, R3/name-rule fixes, repo-hygiene pass

- **Section 106(ב) re-deposit detection** (`mavat_diff.py`): surfaces the plan's own
  stage-history label when a status change is actually a 106(ב) re-deposit, instead of the
  generic status bucket both cases share. New `mavat_changes.status_detail` column.
- **Silent-empty-vault sanity backstop**: `mavat_diff.py` now hard-fails if
  `load_tracked_plans()` returns fewer than 1000 plans, instead of silently diffing
  against a mid-rebuild/truncated `projects.db`.
- **`docs/TRAINEE_GUIDE.md`** added — top-to-bottom onboarding explainer.
- **R3 auto-exclusion fixed** to require a confirmed real unit count, not the default
  placeholder; `בית פרטי (צמוד קרקע)` name-rule broadened; a stale-browser-cache bug that
  kept un-excluded plans showing "excluded" indefinitely was fixed. See
  `docs/BUG_REFERENCE.md` for all three.
- **Repo-hygiene pass**: the repo had zero commits since 2026-07-13 across five sessions
  of real work; retroactively documented the missing 07-19 session, removed a stray
  malformed output file, and committed everything accumulated (excluding two superseded
  rural-planning spreadsheet files, left untracked per the 2026-07-16 decision).

## 2026-07-15/16 — Single-page review architecture, real unit/description detection, two data bugs fixed

- **Unified 9-status whitelist** now governs new-candidate discovery, vault-notices, and
  status-change tracking together (previously three separate, drifting lists): `הכנת הודעה
  77/78`, `הכנת תכנית`, `Pre-Ruling`, `תסקיר סביבתי`, `בבדיקת תנאי סף`, `בבדיקה תכנונית`,
  `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה`. One-time migration recomputed
  `target_status` for all existing rows; the resulting historical-backlog flood (~14.5k
  candidates, then 1,613 vault-notices) was bulk-dismissed per user decision, tagged and
  auditable, so only genuinely new plans reaching these statuses surface going forward.
- **`mavat_review.html` merged into a single page** — added `vault_notice` (a vault-tracked
  plan's first Mavat appearance, one-click dismiss) and `status_change` (absorbs the
  retired `mavat_changes.html`, keyed `chg::<id>`) row kinds alongside the existing
  `candidate` kind. `make_changes_page.py`, `apply_changes.py`, `mavat_changes.html`
  deleted; their logic lives in `make_review_page.py`/`apply_review.py` now.
- **`mavat_discover_units.py`** (new file): fetches real per-plan unit counts via the SV4
  detail page (the `--tag-units` sweep was a stale one-off snapshot from 2026-07-12 —
  confirmed a real bug on `302-1493931`, tagged <10 units but actually 300). Same fetch
  also reads the plan's free-text description (`recExplanation.EXPLANATION`) and
  un-excludes an R3-excluded candidate when the text signals a sizeable project despite no
  parseable unit count (keyword list + >10-dunam land-area check, both user-approved) —
  confirmed on `259-1374917`. Runs as an ongoing daily step in `run_discovery.bat`.
- **Two real bugs found and fixed** (see `docs/BUG_REFERENCE.md`): a SQL `NOT LIKE`
  filter silently hid every open candidate for a day (NULL-handling), and
  `status_date`/`decision_date` were swapped in the Mavat field mapping, causing
  false-positive status-change entries.
- **`RefreshProjectsDB` scheduled task fixed**: was calling bare `python` (PATH lookup,
  had started failing) instead of a full interpreter path like the other three tasks.
- Applied a 2,959-decision review batch: 2,885 excluded, 60 kept (queued for manual vault
  entry), 7 vault-notices dismissed, 3 status-changes approved (vault written,
  `projects.db` refreshed automatically).

## 2026-07-08 — Documentation framework + Mavat prototype

- Established the project documentation framework (mirrors the Transit_Score layout):
  `README.md`, `CLAUDE.md`, `next_steps.md`, `SETUP.md`, `docs/` (DATA_FLOW, SCHEMAS,
  BUG_REFERENCE, VERSION_LOG, MAVAT_AUTOMATION, moved spec docs), `docs/session_handoffs/`,
  `memory/MEMORY.md`.
- Moved loose root `.md` files into `docs/` (`framework_spec`, `structure_proposal`,
  `vocab_review`, `HANDOFF_vault_pipeline`, and the Mavat findings → `MAVAT_AUTOMATION.md`).
- **Mavat scraper prototype** (`mavat_scraper/`): headless Playwright confirmed working against
  the WAF; search-only status extraction (`mavat_status.py`). Benchmarks ~7s cold / ~6s warm.
- **Housekeeping**: moved core pipeline to `scripts/` and updated the `RefreshProjectsDB` task
  (verified it rebuilds all 5 tables end-to-end); removed redundant `projects_from_notes.db`
  (proven a strict subset of `projects.db`); removed one-off Mavat probes.
- Verified DB shape: five tables (`projects`, `status_events`, `tenders`, `signatures`,
  `value_history`) built by `scripts/refresh_db.py` — the earlier "single table" note was an
  inspection bug (see BUG_REFERENCE.md).

## 2026-07-06 — Mavat source research

- Confirmed Mavat is the authoritative plan-status source; plain HTTP / ArcGIS endpoints are
  WAF-blocked (F5-style challenge). Documented in `docs/MAVAT_AUTOMATION.md`.

## Earlier — Vault → DB pipeline (dates approximate)

- `build_db.py` / `refresh_db.py` pipeline: structured vault → `projects.db` (~10,507 projects).
  33-code status vocabulary, derived numeric fields, `project_type` classification.
- One-time migration of the vault to the structured (Dataview inline-field) format via
  `structure_vault.py`. `parse_vault.py` (prose parser) retired.
- `RefreshProjectsDB` scheduled task created (daily 06:00).
