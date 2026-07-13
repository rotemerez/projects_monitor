# Schemas — Database & Status Vocabulary

**Last Updated:** 2026-07-08

Authoritative code reference: `scripts/build_db.py` (`STAGE_VOCAB` / `STAGE_LABEL`) and the
`CREATE TABLE` block in `scripts/refresh_db.py`. Full spec: `framework_spec.md`.

---

## `projects.db` — as currently built (verified 2026-07-08)

**Five tables**, built by `scripts/refresh_db.py` from the structured vault. Approximate row
counts (latest vault build 2026-07-08): `projects` 10,516 · `status_events` 12,026 ·
`tenders` 2,426 · `signatures` 7,131 · `value_history` 2,354. (The redundant
`projects_from_notes.db` — a strict subset — was removed 2026-07-08.)

### Table: `projects`
| Column | Meaning |
|---|---|
| `project_id` | PK |
| `city` | city (from vault folder) |
| `note` | orphan/free note (`הערה::`), flagged text |
| `project_name` | project title (usually includes developer in parentheses) |
| `plan_current` | current (non-struck) plan number — **Mavat join key** |
| `plan_raw` | raw plan field incl. struck-through history |
| `tender_raw` | raw tender field (`מחוז/מספר/שנה`, e.g. `ים/212/2025`) — **רמ"י join key** |
| `request` | permit request (`בקשה::`) |
| `developers` | `יזמים::` |
| `description` | free-text `תיאור::` (source for numeric extraction) |
| `status_raw` | raw status timeline (stage + date events) |
| `exec_forecast` | `צפי לביצוע` (start-of-construction forecast) |
| `occupancy_forecast` | `צפי לאכלוס` (occupancy forecast) |
| `extra` | misc leftover |
| `relpath` | source file path (provenance) |
| `project_type` | derived: `state_land` / `urban_renewal` / `combination` / `municipal` / `unknown` |
| `existing_units` | derived — evacuated/demolished units only |
| `new_units` | derived — new units (per counting rules in framework_spec) |
| `commercial_sqm`, `office_sqm`, `public_sqm`, `industrial_sqm`, `mixed_use_sqm` | derived sqm by use |
| `floors_max` | derived max floors |

> **Numeric fields are estimates** (marked `·משוער` in the vault) — human verification expected.

## Normalized side-tables (built — one row per instance, keyed by `project_id`)

Stage-mapping coverage is ~92% (11,102 / 12,026 status events mapped to a canonical code).

### `status_events` — the Mavat diff target
`id`, `project_id`, `seq`, `raw` (verbatim status line), `stage_code`, `stage_label`
(canonical Hebrew), `date_norm`, `date_precision`, `is_current` (1 = latest event by date, or
the line marked `(נוכחי)` in the vault). Indexed on `project_id`.

### `tenders`
`id`, `project_id`, `tender_no`, `district_code`, `district`, `serial`, `year`, `status`
(`published`/`won`), `date_published`, `date_awarded`, `winner`, `raw`. Indexed on `tender_no`.

### `signatures`
`id`, `project_id`, `percent`, `date_norm`, `date_precision`, `raw`.

### `value_history`
`id`, `project_id`, `field`, `old_value` (struck-through / superseded value), `raw_context`.

## Status vocabulary — 33 canonical codes (`code → Hebrew label`)

Source of truth: `STAGE_LABEL` in `build_db.py`.

**Renewal / pre-statutory**: `owner_engagement`=התקשרות עם בעלי זכויות ·
`developer_selection`=בחירת יזם ע"י בעלי הזכויות · `combination_deal`=עסקת קומבינציה ·
`acquisition`=רכישה/מכירה · `renewal_area_declared`=הכרזת מתחם מועדף · `track_declared`=מסלול תכנון

**Statutory planning**: `pre_planning`=תכנון מוקדם · `thresholds`=עמידה בתנאי סף ·
`pre_ruling`=פרה רולינג · `round_table`=שולחן עגול · `planning_review`=בדיקה תכנונית ·
`submitted`=הגשה למחוזית · `local_recommend`=המלצת מקומית להפקדה · `pre_deposit`=טרום הפקדה ·
`deposit_conditioned`=הפקדה בתנאים · `deposited`=פרסום הפקדה · `objections`=דיון בהתנגדויות ·
`amendment_106b`=תיקון לפי 106ב · `publication_77_78`=פרסום לפי 77-78 ·
`approved_conditioned`=אישור בתנאים · `approved`=אישור · `validity_extension`=הארכת תוקף ·
`plan_stopped`=עצירת/דחיית תכנית · `preservation_committee`=ועדת שימור

**Tender**: `tender_published`=פרסום מכרז · `tender_won`=זכייה במכרז

**Permit / execution**: `info_file`=תיק מידע · `permit_request`=בקשה להיתר ·
`permit_conditioned`=היתר בתנאים · `permit_granted`=היתר בנייה · `design_plan`=תכנית עיצוב/בינוי ·
`site_prep`=הריסה/עבודות הכנה · `under_construction`=בנייה · `completed`=סיום בנייה

## Mavat → vocabulary mapping (TODO)

The scraper returns `INTERNET_STATUS_CODE` (numeric, e.g. `4480`, `7890`) and
`UNIFIED_STATUS_DESC` / `INTERNET_SHORT_STATUS` (Hebrew). Mapping these onto the 33 codes above
is an open task (next_steps Phase 2). Examples seen:
- `אישור` / `פרסום אישור` (code 4480) → `approved`
- `הפקדה להתנגדויות/השגות` (code 7890) → `deposited` / `objections`
- `הכנת הודעה 77/78` → `publication_77_78`
