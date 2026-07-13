# Next Steps — Projects Vault → DB & Mavat Automation

**Last Updated:** 2026-07-13 (evening)

Living task-tracking document. Newest section on top. Check items off as they land.

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
- [ ] **Bartech excluded for now** — separate, unrelated breakage: Chrome auto-updated
      past the pinned ChromeDriver in `local_committee_scrapers`' Selenium-based Bartech
      scraper. Lead (not yet pursued): `C:\R_PROJECTS\Project_update_scraper`'s Bartech
      *permit* scraper found Bartech's CAPTCHA isn't server-enforced and scrapes via
      plain HTTP; a network capture confirmed Bartech's *plans* search also fires real
      XHR/POST requests, suggesting the same scraper could be rewritten as pure HTTP
      instead of patching ChromeDriver. Full detail in `docs/MAVAT_AUTOMATION.md`.
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
- [x] **Change-approval flow** (2026-07-13, user request): `mavat_changes.html`
      (`make_changes_page.py`) — review detected status changes, אשר/דחה + comment,
      export decisions JSON. `apply_changes.py <json>` appends approved changes as
      `- סטטוס:: <label> <date>` to the correct vault block (found via `תכנית::`),
      migrates the `(נוכחי)` marker, refuses duplicates, then reruns `refresh_db.py`.
      Sandbox-tested on a vault copy. **Only user-approved changes ever reach the vault.**
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
      early status (final target set: בבדיקה תכנונית, בבדיקת תנאי סף, תסקיר סביבתי,
      הכנת הודעה 77/78, Pre-Ruling). Backfilled since 01/01/2022 via recursive
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
- [x] **Scheduled**: Task Scheduler `MavatDiscovery` — weekly Sunday 07:30,
      `run_discovery.bat` (sweep since last run → `auto_rules.py --units-rule` →
      regenerate `mavat_review.html`; log → `discovery_last.log`).
- [ ] **Ongoing manual loop**: review `mavat_review.html` → export decisions →
      `apply_review.py` → enter **kept** plans into the vault by hand (queue currently
      22 plans, sorted by decision date) → next 06:00 rebuild picks them up as tracked.
      Currently ~1,504 open candidates being worked through (post-backfill backlog).

### Phase 3b: Local-committee discovery — BUILT 2026-07-13 (see top section)

---

## Backlog — Vault → DB pipeline

- [x] Side-tables (`status_events`/`tenders`/`signatures`/`value_history`) verified
      built by `scripts/refresh_db.py` (~92% stage mapping).
- [x] De-duplicated: `projects_from_notes.db` was a strict subset, removed.
- [ ] `project_type == unknown` (~34% of projects): `build_db.derive_type()` falls
      through to `unknown` when none of its four positive rules match text/developer
      fields (`state_land`, `urban_renewal`, `combination`, `municipal`) — mostly plain
      private-initiative projects on private land with no distinguishing keywords, not
      missing data. Refine the heuristic later if it starts mattering for analysis.
- [ ] Decide whether to keep the `·משוער` (estimated) marker on derived fields in the vault.

---

## Housekeeping

- [x] `Daily Projects Report Download` scheduled task (Madlan back-office CSV export,
      separate from this project) had been failing nightly since 2025-12 —
      **disabled by user 2026-07-13**.
- [ ] Delete obsolete one-off logs in `mavat_scraper\`: `all_run*.log`,
      `backfill_run*.log`, `tagunits_run*.log`, `discover_run*.log` (superseded by
      `status_diff_last.log` / `discovery_last.log`).

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
