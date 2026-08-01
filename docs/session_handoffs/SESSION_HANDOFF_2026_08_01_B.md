# Session Handoff — 2026-08-01 B

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_08_01_A.md` (same day, second session). That handoff
left two untracked decisions-export files sitting on disk, unapplied, and open questions
about whether any new auto-rules could be mined from them — this session did both.

## What was built / fixed

1. **Applied both pending `mavat_review_decisions` exports** via `apply_review.py`:
   - `(6).json` — 11,905 decisions (1,944 mavat, 9,947 committee, 14 status-changes):
     11,733 excluded, 151 kept, 7 vault-notices dismissed, 5 status-changes approved
     (written to the vault), 1 rejected.
   - `(7).json` — 20,673 decisions (2,376 mavat, 18,266 committee, 31 status-changes):
     confirmed to be a cumulative superset of `(6)` (same `mavat_state.db`, so all 31
     status-change ids were already resolved by the `(6)` run) — 20,319 excluded, 292
     kept, 31 vault-notices dismissed, 0 *new* status-changes.
   - One approved status-change, `503-1487552` (Givatayim, פועלי הרכבת), could not be
     written to the vault — `append_status()` couldn't find its `תכנית:: 503-1487552`
     line in that project's markdown file. Left pending rather than guessed at — **see
     open loops below**.
   - `scripts/refresh_db.py` rerun afterward: `projects.db` now 10,710 projects / 12,332
     status events / 11,403 mapped / 2,443 tenders / 7,132 signatures.
   - Per the user's decision, the two JSON files (and the two untracked rural-planning
     spreadsheets from 2026-07-15/16) were **left on disk, not deleted** — next real
     export can be de-duplicated against them if needed.

2. **New auto-rule R7** (`mavat_scraper/auto_rules.py`, mavat-only): mined the
   manual-exclusion comments (state=`excluded` with no automatic reason) in both files
   for new rule candidates, the same method that found R6 on 2026-07-22. Two patterns
   surfaced:
   - **R7 (implemented)**: Arab towns under the "עירון" regional council — Umm al-Fahm,
     Baqa al-Gharbiyya, Jatt. 319 excluded vs. 4 kept in the historical data, and all 4
     kept plans had either "שכונ" in the name or a confirmed 100+ unit count — matching
     explicit user comments ("like bedouin munis, ignore point plans", "לא מעוניין
     בתכניות עם פחות מ-100 יח\"ד בישובים ערביים"). Implemented as the same shape as the
     existing Bedouin-town rule (R2/`BEDOUIN_TOWNS`), but with a real, checkable 100-unit
     bar instead of a boolean ≥10 flag — required threading the actual `units` count
     (not just `units_ge10`) through `apply_to_mavat()` into `classify()`.
     `ARAB_COUNCIL_LOCATIONS = ["עירון"]`, `ARAB_COUNCIL_UNIT_THRESHOLD = 100`. Two other
     Arab-town locations (מבוא העמקים, הגליל המזרחי) had only a single occurrence each —
     deliberately left out as too thin. Dry-run verified against live `mavat_discovery.db`
     rows before applying for real: 7 candidates excluded, all correctly matching the
     "no שכונ, no confirmed 100+ units, no other override" shape; the plans that stayed
     open all had a genuine positive signal (e.g. "מתחם" multi-hundred-unit projects, or
     an explanation field mentioning "שינוי ייעוד"/commercial content).
   - **Rural single-lot pattern (NOT implemented — user's explicit call)**: 11 manual
     rejections of single-lot/single-unit rights additions inside a kibbutz/moshav,
     spread across 8 different regional councils (מטה יהודה, גולן, שדות דן, עמק יזרעאל,
     חוף השרון, מנשה-אלונה, כפר ביל"ו, עמק המעיינות — 1-2 each). Presented three options
     (skip / build a regional-council name list from general knowledge / a narrower
     content-only regex); user chose **skip**. Reasoning to preserve: a location-list
     approach here would mean inventing ~50 Israeli regional-council names from outside
     the actual review history, unlike R6 which was built from real per-council rejection
     counts (thousands each, 0% keep rate) — a categorically weaker evidence base. Revisit
     only if this pattern accumulates more data points in future exports.

## Decisions made (should not be re-litigated)

- **R7's scope is intentionally narrow**: only "עירון" (Iron), not the two other
  single-occurrence Arab-town locations. Don't broaden without more evidence.
- **The rural single-lot pattern was deliberately NOT turned into a rule.** Don't
  re-attempt this from general Israeli-geography knowledge — if it's worth automating,
  it should be built the same way R6/R7 were: from the user's own accumulated rejection
  counts in a future decisions export, not invented ahead of the data.
- **The two decisions JSON files stay on disk** (not deleted) specifically so a future
  export can be de-duplicated against them — this is a standing decision, not an oversight.

## Current state / open loops

- **`503-1487552` (Givatayim, פועלי הרכבת) status-change is stuck pending** —
  `mavat_changes` row never got `approved=1` because its vault anchor line wasn't found.
  Needs a manual look at that project's markdown file (plan-number formatting mismatch?)
  before the approval can go through.
- Same open loops as `SESSION_HANDOFF_2026_08_01_A.md` otherwise: Tira/Tzefat not yet
  rescraped under their corrected site_ids; 60 kept plans from 2026-07-16 still awaiting
  manual vault entry; not all Complot municipalities have a confirmed frontend-link
  override yet.
- `docs/rural-planning_index1.xls` / `docs/קובץ יישובים.xlsx` remain untracked, same as
  every prior handoff — still no decision to delete them.

## Files touched this session

- `mavat_scraper/auto_rules.py` — new R7 rule (`ARAB_COUNCIL_LOCATIONS`,
  `ARAB_COUNCIL_UNIT_THRESHOLD`), `classify()` gained a `units` parameter,
  `apply_to_mavat()` now selects the real `units` column.
- `mavat_scraper/mavat_discovery.db`, `committee_scraper/committee_state.db`,
  `mavat_scraper/mavat_state.db` — updated by `apply_review.py` (both decisions files) and
  by the R7 auto-exclusion run (generated state, not committed).
- Vault (`...\שכונות\...`) — 5 status lines appended by the approved status-changes in
  file `(6)`.
- `projects.db` — refreshed from the vault.
- `mavat_scraper/mavat_review.html` — not regenerated this session (no `make_review_page.py`
  run) — will pick up the new state on the next scheduled `CommitteeSweep`/`MavatDiscovery`
  run regardless.
- `CLAUDE.md`, `next_steps.md`, `docs/VERSION_LOG.md` — documented all of the above.
