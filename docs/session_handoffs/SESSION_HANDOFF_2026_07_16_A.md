# Session Handoff — 2026-07-16 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_14_A.md`. Spans 2026-07-15 → 2026-07-16 (one
continuous session). Full detail in `docs/MAVAT_AUTOMATION.md` and `CLAUDE.md` (session
history + scheduled-tasks section, both updated this session).

## What was built / fixed

1. **`RefreshProjectsDB` task fixed**: its Action called bare `python` (PATH lookup) while
   the other three tasks use a full interpreter path — this had started failing with
   `ERROR_FILE_NOT_FOUND`. Repointed to `C:\Users\Rotem\AppData\Local\Programs\Python\
   Python313\python.exe` explicitly, matching the other tasks.

2. **Real per-plan unit counts (`mavat_discover_units.py`, new file)**: the `--tag-units`
   sweep (mavat_discover.py) is a one-off snapshot from 2026-07-12 that never re-ran, so
   any plan whose real unit count only became visible after that date sat permanently
   tagged `units_ge10=0` and got silently auto-excluded by R3 — confirmed on `302-1493931`
   (tagged <10 units, actually 300 real units per Mavat's SV4 detail page). New script
   reuses `MavatSession.fetch_detail` + `mavat_diff.parse_quantities` (same machinery
   already used for `MavatStatusDiff`'s units baseline) to get a live number per plan.
   Targets: (a) candidates just auto-excluded by R3, (b) never-checked open candidates in
   early statuses. Wired into `run_discovery.bat` as an ongoing daily step (`--limit 25`,
   no one-time catch-up requested).

3. **Description-text interpretation, same script**: also reads `recExplanation.EXPLANATION`
   from the SV4 detail JSON (same fetch, no extra request) and un-excludes an R3-excluded
   candidate when the text signals a sizeable project despite no parseable unit count —
   confirmed on `259-1374917` ("...רובע מגורים ותעסוקה... 106 ד' שטח חקלאי..."). Two
   independent signals (either is enough): a user-approved keyword list (quarter/new-
   neighborhood language, mixed residential+employment framing, population-growth framing,
   "hundreds/thousands of units" prose) and a >10-dunam land-area figure regex. New
   `discovered.explanation` column stores the raw text; the specific match reason is only
   printed to `discovery_last.log`, not surfaced in the UI (explicitly deferred by user).

4. **"Vault-notice" mechanism** (new row kind in `mavat_review.html`): a plan already
   tracked in the vault that just appeared in the Mavat sweep for the first time now gets
   a one-time nudge to go check Mavat's page (richer data than the committee source it was
   originally entered from) — distinct badge, single "seen" dismiss action (not
   keep/exclude, since it's already tracked). New `discovered.vault_notice_seen` /
   `_seen_at` columns. Confirmed on `304-1388289` (committee-tracked, first appeared in the
   Mavat sweep 2026-07-15).

5. **Unified 9-status whitelist** (user-specified 2026-07-16, replaces two previously
   separate/narrower lists): `הכנת הודעה 77/78`, `הכנת תכנית`, `Pre-Ruling`, `תסקיר סביבתי`,
   `בבדיקת תנאי סף`, `בבדיקה תכנונית`, `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה` now govern
   ALL THREE surfaces (new-candidate discovery, vault-notices, status-change tracking) —
   kept in sync across `mavat_discover.py:TARGET_STATUSES`, `mavat_diff.py:
   MAVAT_TRACKED_STATUSES`, `make_review_page.py:MAVAT_TRACKED_STATUSES`. Both committee
   statuses (`בתכנון`, `בהפקדה`) always tracked, no filtering.
   - **Migration ran once** (`migrate_target_status.py`, kept as a reference script):
     recomputed `target_status` for all existing rows; ~16k historical `אישור`/`נדחתה`
     rows newly qualified — per user's Option A, auto-excluded the ~14.5k that were
     first_seen before the cutoff (pure migration noise, not real decisions) so only
     genuinely new plans reaching these statuses show up going forward. **Same flood
     re-appeared on the vault-notice channel** (1,613 historical in-vault plans newly
     qualified) and got the identical treatment — worth remembering if the status list
     ever widens again: check BOTH channels, not just candidates.
   - Backlog-tagged rows (`'אוטומטי: סטטוס נכלל לראשונה...'`) are excluded from
     `make_review_page.py`'s payload query entirely (not just hidden client-side) — they
     inflated the page to 12MB before this filter; see the query's comment.

6. **Merged `mavat_changes.html` into `mavat_review.html`** (third row kind,
   `status_change`, keyed `chg::<id>` so it can never collide with a bare plan number or a
   `muni::plan` committee id) — approve writes the vault status line + refreshes
   `projects.db` (logic moved from the now-deleted `apply_changes.py` into
   `apply_review.py`), reject just dismisses. `make_changes_page.py`, `apply_changes.py`,
   `mavat_changes.html` are deleted; `run_status_diff.bat` now calls `make_review_page.py`
   instead.

7. **Two real bugs found and fixed in the date/status-date pipeline**:
   - **NULL-handling bug** (introduced by change #5's backlog filter, found next day):
     `exclude_reason NOT LIKE '...'` evaluates to `NULL` — not true — for every row where
     `exclude_reason IS NULL`, so SQLite silently dropped **every genuinely open
     candidate** from the page, not just the intended backlog noise. This was the full
     explanation for "very few plans for review" and for `102-1477827` being invisible.
     Fixed with `(exclude_reason IS NULL OR exclude_reason NOT LIKE ...)`. **Any future
     `NOT LIKE`/`!=` filter against a nullable column needs the same `IS NULL OR` guard.**
   - **status_date/decision_date field mapping was swapped**: confirmed against a live
     screenshot of `215-1288927`'s Mavat page — the date next to the current status
     (top box) matched `BI_STATUS_DATE`, not `INTERNET_STATUS_DATE` (which instead tracks
     the *latest entry across the whole "שלבי טיפול בתכנית" stage-history table* —
     can advance from unrelated administrative sub-steps without the real status or its
     date moving). Swapped the mapping in `mavat_status.py` (`_extract()`) and
     `mavat_discover.py`; backfilled all 2,029 `mavat_state.db` rows instantly (both
     fields already stored, just swapped columns — no re-scraping needed).
     `mavat_discovery.db`'s `status_date` will self-correct as rows get naturally
     re-touched by future sweeps. Root-caused 4 of 5 pending `שינויי סטטוס לאישור` entries
     as false positives from this exact bug (same status text, only the noisy field had
     moved) — dismissed those 4 (`353-1545854`, `306-1464056`, `302-1306018`,
     `215-1288927`), kept the 1 genuine transition (`216-1534395`,
     `בבדיקה תכנונית → נדחתה`).

8. **Reviewed and applied a 2,959-decision batch** (`mavat_review_decisions (5).json`):
   2,885 excluded, 60 kept (queued for manual vault entry), 7 vault-notices dismissed, 3
   status-changes approved (vault written, `projects.db` refreshed automatically).

## Decisions made (not code changes, but should not be re-litigated)

- **77/78-status plans are NOT to be auto-excluded.** A batch of ~84 stale rejections on
  2026-07-14 at that status looked like a pattern worth automating; it wasn't — those were
  stale duplicates already reviewed, and the user explicitly wants to keep seeing *new*
  77/78-status candidates going forward (early signal of planning intent). I built and then
  reverted an auto-rule for this mid-session; don't re-propose it.
- **Detail-page fetch (`mavat_discover_units.py`) runs ongoing only, no backlog catch-up.**
  User was explicit: ~7s/plan against a WAF-protected site, don't blanket-fetch the
  existing queue.
- **Status-date field mapping fix has no historical `discovered.status_date` backfill.**
  Not worth a live re-scrape just for a display date; it self-heals via normal incremental
  sweeps.
- **Explanation-match reason stays log-only** (`discovery_last.log`), not surfaced on the
  review page — user's call when asked, said they'll click through to Mavat instead.

## Process feedback (how to work with this user)

- **Stop and wait after asking a question — don't continue other work while waiting.**
  Given explicit correction 2026-07-16: an either/or question was asked, then other tool
  calls were made before the user's answer arrived, causing confusion about which answer
  applied to what. Treat any open question as a hard stop until answered.
- **Confirm before implementing new rules/architecture changes** — established repeatedly
  this session (keyword lists, status whitelist scope, backlog-handling approach). Present
  a concrete plan and wait for explicit go-ahead, especially for anything touching the
  scheduled-task pipeline or exclusion logic.
- When pasted JSON/text shows Hebrew mojibake (`×××...`), it's consistently a chat-paste
  decoding artifact, not real data corruption — verify by reading the actual file from disk
  (Downloads folder, matching filename pattern `mavat_review_decisions (N).json`) rather
  than reconstructing from what appears in the conversation. Never write mojibake text back
  into a DB field.

## Current state / open loops

- **Scheduled tasks**: `RefreshProjectsDB` 06:00 (fixed), `MavatStatusDiff` 07:00,
  `MavatDiscovery` 07:30 (now also runs `mavat_discover_units.py --limit 25`),
  `CommitteeSweep` 08:00. All four should be verified healthy tomorrow morning given the
  `RefreshProjectsDB` fix landed today.
- **Kept-plans queue**: 60 fresh Mavat-source + prior committee-source plans awaiting
  manual vault entry (per the last decisions batch).
- **Nothing else currently broken or blocked.** All bugs found this session (SQL NULL
  handling, status-date field swap, R6 auto-rule mistake) were fixed/reverted within the
  same session.
- **Not done, no action requested**: no UI surfacing of the explanation-match reason; no
  historical backfill of `mavat_discovery.db.status_date`; no rural-settlement/dunam
  classifier beyond what's now in `mavat_discover_units.py` (the earlier
  קובץ יישובים.xlsx/rural-planning_index1.xls exploration for a broader rural-locality
  list was superseded by the description-text approach and not carried further — revisit
  only if the text/dunam signals prove insufficient).

## Files touched this session (for quick orientation)

- `mavat_scraper/mavat_discover_units.py` — **new**: real unit counts + explanation-text
  sizeable-project detection, reusing existing detail-fetch machinery.
- `mavat_scraper/mavat_discover.py` — `TARGET_STATUSES` widened to the 9-status whitelist;
  `status_date` now sourced from `BI_STATUS_DATE` not `INTERNET_STATUS_DATE`.
- `mavat_scraper/mavat_diff.py` — `MAVAT_TRACKED_STATUSES` (replaces the old
  `IGNORED_NEW_STATUSES` single-entry ad-hoc rule).
- `mavat_scraper/mavat_status.py` — `status_date`/`decision_date` field-mapping swap.
- `mavat_scraper/make_review_page.py` — vault-notice + status_change row kinds, chip
  filters, NULL-handling fix on the backlog-noise query, `MAVAT_TRACKED_STATUSES` constant.
- `mavat_scraper/apply_review.py` — `seen` (vault-notice) and `chg::` (status-change
  approve/reject, absorbing former `apply_changes.py` vault-write logic) routing.
- `mavat_scraper/run_discovery.bat` — added `mavat_discover_units.py --limit 25` step.
- `mavat_scraper/run_status_diff.bat` — now calls `make_review_page.py` instead of the
  retired `make_changes_page.py`.
- **Deleted**: `mavat_scraper/make_changes_page.py`, `apply_changes.py`,
  `mavat_changes.html` — fully merged into the above.
- `CLAUDE.md` — scheduled-tasks section rewritten to describe the single-page architecture.
- Vault/DB: 2,959 decisions applied (see above); `mavat_state.db` full backfill (status/
  decision date swap); one-time `target_status` migration + two backlog bulk-dismiss passes
  (candidates, then vault-notices).
