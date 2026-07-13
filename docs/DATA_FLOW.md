# Data Flow — Architecture

**Last Updated:** 2026-07-08

How data moves from the human-maintained vault to the analysis DB and the Mavat automation.

---

## Overview

```
   Obsidian Vault (source of truth, Dropbox)
   one file per neighborhood; #### blocks per project; "שדה:: ערך" inline fields
                    │
                    │  scripts/refresh_db.py  (imports scripts/build_db.py core logic)
                    │  - parse blocks & fields
                    │  - normalize status vocabulary (33 codes) + dates
                    │  - parse tenders; extract numeric fields (units, sqm, floors)
                    ▼
   projects.db  (SQLite — analysis/automation layer)
   projects + status_events + tenders + signatures + value_history
                    │
        ┌───────────┴───────────┐
        ▼                        ▼
   projects.csv / .xlsx     Mavat automation  (mavat_scraper/)
   (exports)                for each plan_current:
                             search Mavat -> current status + code + date
                             diff vs. stored status -> change report
                                         │
                                         ▼
                             change alerts / report  (separate layer —
                             NOT written back into the vault notes)
```

## Layer principle (lock v2)

- **Vault = human source of truth.** Stays faithful to how the analyst writes things (original
  wording, strike-through history, original dates). Derived/normalized values are **not**
  written back into notes as if typed.
- **DB = analysis layer.** Holds the normalized/derived forms.
- **Automation output = its own layer.** Alerts, reports, dashboards — never note edits.

See `framework_spec.md` for the full rationale and parsing rules.

## Stage 1 — Vault → DB (`scripts/refresh_db.py` + `scripts/build_db.py`)

- **Input**: the structured vault (produced once by `scripts/structure_vault.py`).
- **`scripts/build_db.py`** holds the core logic: `STAGE_VOCAB`/`STAGE_LABEL` (33 canonical
  stage codes), date normalization + precision, tender parsing, numeric extraction from the
  free-text `תיאור` (description).
- **`scripts/refresh_db.py`** orchestrates: read vault → apply core logic → write the five
  tables of `projects.db`. Reads explicit vault fields (respects manual edits); falls back to
  re-deriving numbers only when numeric fields are absent.
- **Schedule**: `RefreshProjectsDB` task, daily 06:00 (`scripts\refresh_db.py <vault> projects.db`).

## Stage 2 — Mavat automation (`mavat_scraper/`)

- **Join key**: `projects.plan_current` (plan number).
- **Mechanism**: Playwright headless Chromium drives the Mavat search UI (a plain HTTP call is
  WAF-blocked). The `sv3/Search` response row carries the current status, a numeric status code,
  and status/decision dates.
- **Diff**: compare live status vs. `status_events.is_current` (per `plan_current`) → flag
  advances. The diff target exists; wiring the comparison + change report is `next_steps.md`
  Phase 2.
- Detailed findings, benchmarks, and verdict: `MAVAT_AUTOMATION.md`.

## External sources & join keys

| Source | Gives | Join key | Automatable? |
|---|---|---|---|
| מנהל התכנון (Mavat) | plan status, stages, dates | `plan_current` | Yes (headless browser) |
| רמ"י (tenders) | tender publish/award/winner | tender no. `מחוז/מספר/שנה` | Yes (not built) |
| Press / manual | signatures, developer selection, forecasts | — | No (manual) |
