# Version Log

**Last Updated:** 2026-07-08

Release / change history, newest on top.

---

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
