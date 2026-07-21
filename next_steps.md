# Next Steps — Projects Vault → DB & Mavat Automation

**Last Updated:** 2026-07-21

Living task-tracking document. Newest section on top. Check items off as they land.

---

## Active — 106(ב) detection, sanity backstop, and R3/name-rule fixes — BUILT 2026-07-19/21

- [x] **Section 106(ב) re-deposit detection** (`mavat_diff.py`, 2026-07-19): Mavat's status
      bucket shows the same generic `הפקדה להתנגדויות/השגות` for an original deposit and a
      106(ב) re-deposit of corrections — `find_status_detail()` reads the plan's own
      stage-history log to surface the more specific label when present (found on
      `503-1487552`). New `mavat_changes.status_detail` column, threaded through
      `make_review_page.py`/`apply_review.py`.
- [x] **Silent-empty-vault sanity backstop** (`mavat_diff.py:main()`, 2026-07-19):
      `load_tracked_plans()` returning <1000 plans now hard-fails instead of silently
      running against a mid-rebuild/truncated `projects.db` — root-caused a real missed
      status change (`414-1294818`).
- [x] **`docs/TRAINEE_GUIDE.md`** (new, 2026-07-19): top-to-bottom onboarding explainer.
- [x] **R3 (units<10) now requires a CONFIRMED real unit count** (`auto_rules.py`,
      2026-07-21): was firing on the default `units_ge10=0` placeholder before
      `mavat_discover_units.py` ever fetched a real count — root-caused on `416-1448794`
      (real units=15, wrongly excluded day one). Unconfirmed low counts now leave the plan
      open instead of guessing.
- [x] **`בית פרטי (צמוד קרקע)` name-rule broadened** (`auto_rules.py`, 2026-07-21):
      "צמוד קרקע" alone is now enough, no family-type qualifier required (found on
      `422-0907329`); `POSITIVE_SIGNAL` override still protects genuine multi-unit plans.
- [x] **Stale browser-cache bug fixed** (`make_review_page.py`, 2026-07-21): an
      auto-excluded plan un-excluded server-side (rule fix/backlog reopen) was stuck
      "excluded" forever in an already-open browser tab — only `אוטומטי:`-tagged decisions
      now re-sync from the DB on every page load; human decisions are never touched.
- [x] **Repo-hygiene pass (2026-07-21)**: found the repo had zero commits since 2026-07-13
      despite five sessions of real work; wrote the missing 07-19 handoff retroactively,
      removed a stray malformed output file (`mavat_scraper/..mavat_report.md`), and
      committed everything accumulated (excluding the two superseded rural-planning
      `.xls`/`.xlsx` files — see the note below). See `docs/session_handoffs/
      SESSION_HANDOFF_2026_07_19_A.md` and `..._2026_07_21_A.md`.

---

## Active — Single-page review + real unit/description detection — BUILT 2026-07-15/16

- [x] **Unified 9-status whitelist** (user decision) now governs new-candidate discovery,
      vault-notices, and status-change tracking together: `הכנת הודעה 77/78`,
      `הכנת תכנית`, `Pre-Ruling`, `תסקיר סביבתי`, `בבדיקת תנאי סף`, `בבדיקה תכנונית`,
      `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה` — kept in sync across
      `mavat_discover.py:TARGET_STATUSES`, `mavat_diff.py:MAVAT_TRACKED_STATUSES`,
      `make_review_page.py:MAVAT_TRACKED_STATUSES`. **Explicitly NOT auto-excluded**:
      77/78-status plans — an earlier attempt to treat a batch of stale rejections at that
      status as an auto-rule pattern was reverted; the user wants new 77/78 candidates to
      keep surfacing as an early planning-intent signal.
- [x] One-time migration (`migrate_target_status.py`) recomputed `target_status` for every
      existing row; bulk-dismissed the resulting historical-backlog flood on BOTH the
      candidate channel (~14.5k) and the vault-notice channel (1,613) per user's Option A
      (only plans first_seen before the cutover), so only genuinely new plans surface.
- [x] **`mavat_review.html` merged into one page**, three row kinds: `candidate` (as
      before), `vault_notice` (a vault-tracked plan's first Mavat appearance — one-time
      "go check Mavat" nudge, single dismiss action, new
      `discovered.vault_notice_seen`/`_seen_at` columns), `status_change` (absorbs the
      retired `mavat_changes.html`, keyed `chg::<id>`). `make_changes_page.py`,
      `apply_changes.py`, `mavat_changes.html` **deleted** — logic merged into
      `make_review_page.py`/`apply_review.py`; `run_status_diff.bat` now calls
      `make_review_page.py`.
- [x] **`mavat_discover_units.py`** (new): fetches real per-plan unit counts via the SV4
      detail page — the `--tag-units` sweep was a stale one-off snapshot from 2026-07-12,
      confirmed a real bug (`302-1493931`: tagged <10 units, actually 300). Also reads
      the plan's free-text description (`recExplanation.EXPLANATION`) and un-excludes an
      R3-excluded candidate when the text signals a sizeable project despite no
      parseable unit count (keyword list + >10-dunam check, both user-approved — see
      `docs/MAVAT_AUTOMATION.md`). Runs ongoing (not backlog catch-up) as a daily step in
      `run_discovery.bat`.
- [x] **Two real bugs found and fixed** (see `docs/BUG_REFERENCE.md`): a SQL `NOT LIKE`
      filter silently hid every open candidate for a day (nullable-column NULL-handling);
      `status_date`/`decision_date` were swapped in the Mavat field mapping, causing
      false-positive status-change entries (backfilled `mavat_state.db` for free).
- [x] `RefreshProjectsDB` scheduled task fixed — was calling bare `python` (PATH lookup,
      had started failing) instead of a full interpreter path.
- [x] Applied a 2,959-decision review batch (2,885 excluded, 60 kept, 7 vault-notices
      dismissed, 3 status-changes approved).
- [ ] Not pursued further (superseded by the description-text approach): a data-driven
      rural-settlement classifier from `docs/קובץ יישובים.xlsx` +
      `docs/rural-planning_index1.xls` (name-matching had gaps — spelling variants,
      regional-council names). Revisit only if the text/dunam signals in
      `mavat_discover_units.py` prove insufficient.
- [ ] Detail, file-by-file, in `docs/MAVAT_AUTOMATION.md` → "Single-page architecture +
      real unit/description detection" section; full narrative in
      `docs/session_handoffs/SESSION_HANDOFF_2026_07_16_A.md`.

---

## Active — Local-committee discovery — BUILT 2026-07-13 (Complot side)

- [x] Diagnosed the 2026-06-24 Complot outage: `ConnectionResetError 10054` = server-side
      rate-limiting under a full-133-municipality weekly burst against the shared
      `handasi.complot.co.il` backend, not a permanent block (host healthy on retest).
- [x] Built `projects_monitor/committee_scraper/` — daily rotation (10 Complot
      municipalities/day, ~1 week/cycle) that invokes `local_committee_scrapers`'
      existing code (new additive `run_subset.py` entry point there, no existing files
      touched) and imports results into `committee_state.db`. Spreading the load daily
      is the actual fix for the rate-limiting, not just gentler scheduling.
- [x] **Dedup with Mavat** (user decision): a committee candidate whose קישור למבאת
      (Mavat link) is populated, or whose plan number matches the vault, is
      auto-"graduated" (excluded, reason + link kept) — local-committee tracking stops
      once a plan enters the Mavat pipeline. Verified live: Haifa, 238 plans, 124
      auto-graduated, 114 genuinely new.
- [x] **Unified into the same review page** (user decision): `make_review_page.py` now
      merges `mavat_discovery.db` + `committee_state.db` into one `mavat_review.html`,
      source-tagged with a filter chip; `apply_review.py` routes decisions to the
      correct DB by id shape (`muni::plan_number` vs bare plan number).
- [x] **Scheduled**: Task Scheduler `CommitteeSweep` — daily 08:00,
      `committee_scraper\run_committee_sweep.bat`; log `committee_sweep_last.log`.
- [x] Disabled the old `Municipal Plans Weekly Update` task (superseded, not duplicated).
- [x] **Bartech fixed (2026-07-14)** — rewrote `systems/bartech/plans.py` in
      `local_committee_scrapers` to drive Playwright instead of Selenium. The HTTP-rewrite
      lead turned out to be a dead end (Bartech's plans search enforces a real invisible
      reCAPTCHA server-side — confirmed by a live test); plain headless Playwright passes
      that challenge on its own, no solver needed. Real bug was Selenium's ChromeDriver
      needing separate version-pinning against an auto-updating system Chrome — Playwright
      bundles its own Chromium and sidesteps that entirely. `CommitteeSweep` now runs
      `--systems complot,bartech` (the default). Verified live against Holon (497 plans).
- [x] **Mavat-graduation dedup gap fixed (2026-07-14)** — the dedup check only looked at
      the committee scraper's own קישור למבאת column + the vault; it never cross-checked
      `mavat_discovery.db`'s own plan list. Found via a concrete duplicate (Ashdod
      603-1218759). Added `reconcile_with_mavat_discovery()`, now run every `CommitteeSweep`
      against *all* open candidates (not just newly-scraped ones). Backfilled 35
      already-affected rows once by hand.
- [x] **`auto_rules.py` extended to committee candidates (2026-07-14)** — previously only
      ever touched `mavat_discovery.db`. Added R4 (non-local plan-number format — national/
      old-format plans out of scope at committee level, tracked via Mavat instead — 83% of
      the open queue) and R5 (test/placeholder rows). Wired into `run_committee_sweep.bat`
      too. Open committee queue: 205 → 0.
- [x] **Export-button Hebrew corruption fixed (2026-07-14)** — `mavat_review.html` /
      `mavat_changes.html` exports had no UTF-8 BOM/charset, so Hebrew got mangled by
      codepage auto-detection downstream. Added BOM + explicit charset to both export
      buttons; `apply_review.py`/`apply_changes.py` now read with `utf-8-sig`. Verified
      end-to-end with a Playwright click-through test.
- [ ] Full detail, file-by-file, in `docs/MAVAT_AUTOMATION.md` → "Local-committee
      discovery integration" section.

---

## Active — Mavat status automation

### Phase 1: Prototype — DONE (2026-07-06..09)
- [x] Playwright + Chromium scraper (`mavat_scraper/mavat_status.py`); headless works,
      no stealth needed; ~7s cold / ~6s warm per lookup.
- [x] Fixed two false-miss root causes: generic-search response race, and silently
      failed "כל התכניות" filter click (see `docs/BUG_REFERENCE.md`). Concurrency 3
      verified clean (0 WAF blocks).
- [x] Retry-once-on-miss (fresh session), polite `--delay` (default 2.0s).

### Phase 2: Status diff — DONE, SCHEDULED (2026-07-08..13)
- [x] `mavat_scraper/mavat_diff.py` — batch driver, own state DB (`mavat_state.db`),
      incremental commits, `--plans/--rotate/--all`, dormant-plan skip (אישור/נדחתה or
      vault `approved` → excluded from rotation).
- [x] **Scheduled**: Task Scheduler `MavatStatusDiff` — daily 07:00,
      `run_status_diff.bat` (`--rotate 300 --details 25`, report → `mavat_report.md`,
      log → `status_diff_last.log`).
- [x] **Change-approval flow** (2026-07-13, user request; merged into `mavat_review.html`
      2026-07-16 — see the section at the top of this file): review detected status
      changes, אשר/דחה + comment. Approve appends `- סטטוס:: <label> <date>` to the
      correct vault block (found via `תכנית::`), migrates the `(נוכחי)` marker, refuses
      duplicates, then reruns `refresh_db.py`. **Only user-approved changes ever reach the
      vault.** (The original standalone `mavat_changes.html`/`apply_changes.py` are
      retired; same logic now lives in `make_review_page.py`/`apply_review.py`.)
- [x] **Unit tracking** (2026-07-13): `MavatSession.fetch_detail(mid)` captures the
      SV4 detail XHR; `rsQuantities` gives authorised+added quantities per type; units =
      the מגורים (יח"ד) row. Every detected status change triggers a detail fetch
      (units shown alongside in the report/approval page); `--details 25` per nightly
      run baselines units for plans that don't have one yet (~2 months to full coverage);
      a units-only change (no status change) logs its own approval row.
- [x] **Ignored transitions** (2026-07-13, user decision): `בהליך אישור` never creates
      an approval-page row (user doesn't track it manually) — `IGNORED_NEW_STATUSES` in
      `mavat_diff.py`. Snapshot still updates silently so a later real transition diffs
      correctly against the true prior status.
- [ ] Map Mavat status labels (`UNIFIED_STATUS_DESC`) onto the 33-code `STAGE_LABEL`
      vocabulary — 8 of ~33 codes mapped so far (table in `docs/MAVAT_AUTOMATION.md`);
      grows as more plans get scraped. Then add a vault-vs-Mavat mismatch section
      to the report.
- [x] Investigated the persistent misses (2026-07-08/09): mostly early-stage vault plan
      numbers not yet in Mavat's public index (pre-submission urban-renewal projects);
      they recheck at the rotation tail automatically.

### Phase 3: New-plan discovery (Mavat side) — DONE, SCHEDULED (2026-07-09..13)
- [x] `mavat_scraper/mavat_discover.py` + `mavat_discovery.db` — nationwide sweep by
      early status (target set widened to the unified 9-status whitelist 2026-07-15 —
      see the section at the top of this file). Backfilled since 01/01/2022 via recursive
      plan-prefix slicing (site caps any result list at ~1,470 rows).
- [x] `make_review_page.py` → **`mavat_review.html`** — interactive review page:
      status/units-10+/"new since last sweep"/source chips, open/kept/excluded filters
      (defaults to open-only), kept-queue sorted by decision date, and a
      "סמן הכל כנצפה" watermark so badges survive any number of missed sweeps.
      `apply_review.py <decisions.json>` ingests exported decisions. (2026-07-13:
      extended to merge in committee-sourced candidates too — see the section above.)
- [x] `auto_rules.py` — automatic exclusions from user review patterns (round 1+2):
      technical-plan name patterns (חלוקת מגרשים, שינוי קו בניין, הסדרת מצב קיים,
      בריכות/חניה, single religious buildings), Bedouin-settlement non-neighborhood
      plans, units rule (<10 units AND no employment/roads/rail/parks/public-building
      signal, only on submission-stage statuses), energy/solar exclusion. All tagged
      `אוטומטי: ...`, auditable/revertible in the review page.
- [x] Units tagging (`--tag-units 10`): 6,473/22,522 records since 2022 clear ≥10 units;
      confirmed candidates get a `10+` badge.
- [x] **Scheduled**: Task Scheduler `MavatDiscovery` — **daily 07:30** (changed from
      weekly Sunday, 2026-07-14), `run_discovery.bat` (sweep since last run →
      `auto_rules.py --units-rule` → regenerate `mavat_review.html`; log →
      `discovery_last.log`). `auto_rules.py` now also sweeps committee candidates (see
      "Local-committee discovery" section below).
- [x] 2026-07-14 batch of 22 kept plans reviewed by hand; 3 entered into the vault
      (תמל/1131, תמל/2073, 152-1085646 — confirmed via `refresh_db.py` rerun, now in
      `projects.db`), the other 19 deliberately left untracked. This is a recurring
      loop, not a one-time task — see below.
- [x] Applied 15 pending Mavat status changes via `mavat_changes.html`/`apply_changes.py`
      (2026-07-14): 7 approved (written to vault + `projects.db` refreshed), 7 rejected,
      1 already-applied skip. Queue back to 0 pending.
- [ ] **Ongoing manual loop**: review `mavat_review.html` (now candidates + vault-notices
      + status-changes in one page) → export decisions → `apply_review.py` → enter
      whichever **kept** plans you actually want tracked into the vault by hand → next
      06:00 rebuild picks them up. 60 kept plans from the 2026-07-16 batch still awaiting
      manual vault entry.

### Phase 3b: Local-committee discovery — BUILT 2026-07-13 (see top section)

---

## Backlog — Vault → DB pipeline

- [x] Side-tables (`status_events`/`tenders`/`signatures`/`value_history`) verified
      built by `scripts/refresh_db.py` (~92% stage mapping).
- [x] De-duplicated: `projects_from_notes.db` was a strict subset, removed.
- [x] Decided (2026-07-14): `project_type == unknown` (~34% of projects) is **not a task
      to track**. Nothing in the codebase consumes `project_type` — it's a derived field
      with zero downstream readers, not something the user asked for. Not revisiting
      unless a concrete need to filter/report by project type shows up.
- [x] Decided (2026-07-14): keep the `·משוער` (estimated) marker on derived fields in the vault.

---

## Housekeeping

- [x] `Daily Projects Report Download` scheduled task (Madlan back-office CSV export,
      separate from this project) had been failing nightly since 2025-12 —
      **disabled by user 2026-07-13**.
- [x] Deleted obsolete one-off logs in `mavat_scraper\` (2026-07-14): `all_run*.log`,
      `backfill_run*.log`, `tagunits_run*.log`, `discover_run*.log` (superseded by
      `status_diff_last.log` / `discovery_last.log`).
- [x] Fixed a vault content corruption (2026-07-14, spot-checked by user): AZUR שלב א'
      קפלן 3 ו-5 (אזור, יצחק שדה.md) had a Maya/TASE report URL whose query string got
      saved with literal line breaks, each fragment parsed as its own bogus `- צפי::`
      bullet. Merged back to one line, dropped the URL per user's call. `refresh_db.py`
      rerun confirmed `exec_forecast` is clean. One-off fix, not a systemic parser bug —
      no other instances searched for, since the corruption pattern is specific to a
      pasted URL with embedded newlines.

---

## Notes / decisions
- Old-format Hebrew plan numbers: **out of scope** for status updates and not
  prefix-sliceable for discovery (decided 2026-07-08).
- Committee-decision history: **not needed** for the quick daily check (status + date
  suffice).
- Vault stays faithful to the human source; automation output goes to a **separate
  layer** (report/review pages), and only reaches the vault via explicit per-item user
  approval (`apply_review.py` / `apply_changes.py`) — never silently back-written.
- בהליך אישור is not manually tracked → suppressed from the change-approval queue
  (2026-07-13).
