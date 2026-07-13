# Session Handoff — 2026-07-13 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_12_A.md`. Full detail in `docs/MAVAT_AUTOMATION.md`
and `CLAUDE.md` (scheduled-tasks section).

## What was built

1. **Change-approval flow + unit tracking** (Mavat status side): `mavat_changes.html`
   (approval page for detected status changes) + `apply_changes.py` (approved changes
   write to the vault as `- סטטוס::` lines, then `refresh_db.py` reruns). Unit counts
   parsed from Mavat's SV4 detail XHR (`rsQuantities`), tracked alongside status changes.
   `בהליך אישור` transitions suppressed from the approval queue (user doesn't track it
   manually) — snapshot still updates silently so later real transitions diff correctly.

2. **Local-committee discovery, Complot side, fully built and scheduled**:
   - Root-caused the 2026-06-24 outage: rate-limiting under a one-shot 133-municipality
     weekly burst against Complot's shared backend, not a permanent block.
   - `projects_monitor/committee_scraper/` — daily rotation (10 Complot munis/day) that
     invokes `local_committee_scrapers`' own code (new additive `run_subset.py` there)
     and imports results, with **Mavat-graduation dedup**: a committee candidate whose
     קישור למבאת link is populated (or plan number matches the vault) is auto-excluded —
     "once in Mavat, stop tracking at the committee level" (user's explicit workflow
     description). Verified live: Haifa, 238 plans, 124 graduated, 114 new.
   - Review page (`mavat_review.html`) now merges BOTH discovery sources
     (`mavat_discovery.db` + `committee_scraper/committee_state.db`), source-tagged,
     one filter chip each. `apply_review.py` routes decisions by id shape.
   - Scheduled `CommitteeSweep` (daily 08:00); disabled the old weekly task.
   - **Bartech excluded, unrelated breakage**: Chrome auto-updated past the pinned
     ChromeDriver in that project's Selenium-based Bartech scraper. Lead for a proper
     fix (not pursued yet): `C:\R_PROJECTS\Project_update_scraper`'s Bartech *permit*
     scraper found Bartech's CAPTCHA isn't server-enforced and uses plain HTTP; a
     network capture confirmed Bartech's *plans* search also fires real XHR/POST,
     suggesting the same rewrite is possible there.

3. **Review-page UX fixes**: sticky column-titles-row gap bug fixed (was measuring a
   hardcoded header height; now measures live and re-measures on resize); default view
   is now open-only; a source chip and a "10+ units" chip were added earlier this week
   and remain.

## Current state / open loops

- **Review queue**: ~1,618 open Mavat candidates + 113 open committee candidates (after
  this session's test run), one review page, one export/apply flow.
- **Kept-plans queue**: 21 plans awaiting manual vault entry (sorted by decision date in
  the "נשמרו" view).
- **Pending status changes**: 0 (queue was fully processed this session, including
  suppressing the now-ignored בהליך אישור transitions).
- **Bartech**: not covered by any scheduler; investigate the HTTP-rewrite lead
  mentioned above, or just fix the ChromeDriver/webdriver-manager cache as a stopgap.
- **`Daily Projects Report Download`** (separate, unrelated task): **disabled by user
  2026-07-13** — had been broken since Dec 2025.
- Housekeeping: obsolete one-off logs in `mavat_scraper\` (`all_run*`, `backfill_run*`,
  `tagunits_run*`, `discover_run*`) can be deleted — superseded by the per-task
  `*_last.log` files.

## Files touched this session (for quick orientation)
- `mavat_scraper/mavat_diff.py`, `mavat_status.py` — detail-fetch/units + ignored-status
  suppression.
- `mavat_scraper/make_changes_page.py`, `apply_changes.py` — new.
- `mavat_scraper/make_review_page.py`, `apply_review.py` — extended for dual-source.
- `committee_scraper/run_committee_sweep.py`, `run_committee_sweep.bat` — new module.
- `local_committee_scrapers/.../run_subset.py` — new, additive, in the OTHER project.
- Scheduled tasks: added `CommitteeSweep`; disabled `Municipal Plans Weekly Update`.
