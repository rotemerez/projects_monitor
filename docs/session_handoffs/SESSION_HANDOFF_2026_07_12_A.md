# Session Handoff — 2026-07-12 A (covers 2026-07-09 → 2026-07-12)

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_08_C.md`. Full technical detail in
`docs/MAVAT_AUTOMATION.md`; run `mavat_scraper` scripts with its venv + `PYTHONUTF8=1`.

## What was built: the new-plan DISCOVERY layer (`mavat_scraper/`)

**Goal**: find newly-filed plans nationwide by early status (user's target set:
בבדיקה תכנונית, בבדיקת תנאי סף, תסקיר סביבתי, הכנת הודעה 77/78, Pre-Ruling), surface them
for human review, and iteratively tune automatic exclusion filters from the user's
flag/comment decisions.

- `mavat_discover.py` — sweeps (routine window / `--backfill` prefix-sliced /
  `--tag-units N` / `--count-only` / `--export-json`). Key mechanics in MAVAT_AUTOMATION:
  date field must be TYPED; status dropdown undrivable headless → client-side filter;
  'הצג עוד' caps at ~1,470 rows → recursive plNumber-prefix slicing; responses matched to
  requests by payload; per-query retry with fresh page.
- `mavat_discovery.db` — `discovered` (plan PK; target_status, in_vault, excluded/reason/
  comment, kept, units_ge10, raw JSON), `sweeps` log.
- `make_review_page.py` → `mavat_review.html` — interactive review (RTL, chips, search,
  להזנה/להחריג/הערה, localStorage, יצוא החלטות JSON). **Known fragility**: inline onclick
  handlers may break on names with quote chars — harden if user reports dead buttons.
- `apply_review.py <json>` — ingests decisions (sets excluded/kept), prints reason stats.
- `auto_rules.py` — automatic exclusions tagged 'אוטומטי: ...' (`--dry-run`, `--revert`,
  `--units-rule`). Round 1 applied 2026-07-12: 333 excluded (name patterns + Bedouin
  non-neighborhood rule + positive-signal guard). Rules derived from user's comments.

## State of data (as of this handoff)

- Backfill since 01/01/2022 done: 20,936/22,530 rows (gap = old-format numbers).
- Candidates: 3,183 target-status not-in-vault; 8 manual + 333 auto excluded; 3 kept
  (user enters kept plans into the vault by hand) → ~2,842 open for review.
- User's review decisions JSON round 1 ingested (from Downloads).

## In flight at handoff time (detached processes + monitors armed)

1. **Units tagging sweep** (`--tag-units 10`, PID logged in `tagunits_run.log`) — flags
   plans with ≥10 units (6,473 nationwide since 2022). When done: run
   `auto_rules.py --units-rule --dry-run`, show the user the counts, apply on approval,
   regenerate the review page. R3 only touches submission-stage statuses and skips
   non-residential-looking names.
2. **Status sweep** (`mavat_diff.py --rotate 1600`, log `all_run2.log`) — the tracked-plan
   status baseline; earlier run crashed on a goto timeout at 275/1,847 (now resilient:
   per-plan crash → fresh session → error result). First run's crash also motivated the
   q()-retry wrapper in the discovery backfill.

## Addendum 2026-07-13 — both layers scheduled and validated

- **Status baseline complete**: the resilient `--rotate 1600` run finished (1,336 matched,
  255 misses ≈ the not-yet-on-Mavat early-stage numbers, 9 crash-errors survived).
- **Review rounds 1+2 ingested**: 22 kept plans await vault entry; rules now include
  religious single-sites + energy + units rule; ~1,500 open candidates.
- **New scheduled tasks** (both current-user, wrappers in `mavat_scraper\`):
  - `MavatStatusDiff` — daily 07:00, `run_status_diff.bat` (`--rotate 300`, report →
    `mavat_report.md`, log → `status_diff_last.log`).
  - `MavatDiscovery` — weekly Sunday 07:30, `run_discovery.bat` (sweep since last run →
    `auto_rules.py --units-rule` → regenerate `mavat_review.html`, log →
    `discovery_last.log`).
  - Validated end-to-end via `Start-ScheduledTask`: 127 rows swept, 26 new candidates,
    18 auto-excluded, page regenerated. Net new to review: 8.
- Obsolete one-off logs in `mavat_scraper\` can be deleted when convenient:
  `all_run*.log`, `backfill_run*.log`, `tagunits_run*.log`, `discover_run*.log`.

## Still open

- Status vocab: 8 labels mapped (table in MAVAT_AUTOMATION); vault-vs-Mavat mismatch
  report not yet built.
- Mavat-diff cadence/scheduling decision still deferred (manual runs).
- `local_committee_scrapers` Complot repair (upstream committee-level discovery feed).
- Old-format plans: not status-checked, not discoverable by prefix slicing.
- `Daily Projects Report Download` scheduled task: broken since 2025-12, user wants it
  disabled — needs an elevated shell (`Disable-ScheduledTask`, admin).
