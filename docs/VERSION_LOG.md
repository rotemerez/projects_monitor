# Version Log

**Last Updated:** 2026-08-01

Release / change history, newest on top.

---

## 2026-08-01 — R7 Arab-town unit-threshold auto-rule

- Applied both untracked `docs/mavat_review_decisions (6).json`/`(7).json` exports
  (11,905 and 20,673 decisions, cumulative — the second is a superset) via
  `apply_review.py`: 32,052 exclusions, 443 kept-plan entries, 38 vault-notices dismissed,
  5 status-changes approved and written to the vault (one, `503-1487552`, skipped — plan
  text not found in its vault file, left for manual follow-up). `projects.db` refreshed
  afterward (10,710 projects / 12,332 events).
- Mined the manual-exclusion comments (state=excluded with no automatic reason) across
  both files for new auto-rule candidates, the same way R6 was found on 2026-07-22.
  Two real patterns surfaced; only one was well-evidenced enough to codify:
  - **R7 (new, mavat-only)**: Umm al-Fahm/Baqa al-Gharbiyya/Jatt (all under the "עירון"
    regional council) — 319 excluded vs. 4 kept, all 4 kept containing "שכונ" in the name
    or a confirmed 100+ unit count. Comments were explicit: "like bedouin munis, ignore
    point plans", "לא מעוניין בתכניות עם פחות מ-100 יח\"ד בישובים ערביים". Implemented as
    the same shape as the existing Bedouin-town rule (R2) but with a higher, checkable bar
    (100 confirmed units via the real `units` column, not just the `units_ge10` boolean —
    threaded through `apply_to_mavat`/`classify()` in `auto_rules.py`). Two other
    Arab-town locations (מבוא העמקים, הגליל המזרחי) had only one occurrence each — left
    out, too thin to generalize. Applied once: 7 candidates excluded.
  - **Rural single-lot pattern (NOT implemented)**: 11 manual rejections of single-lot/
    single-unit rights additions inside a kibbutz/moshav, spread across 8 different
    regional councils (2 or fewer each) not covered by the R6 blocklist. User explicitly
    declined to generalize this into a rule — a location-list approach would mean
    inventing a regional-council list from general knowledge rather than reading it off
    real per-council rejection counts (unlike R6). Left as a manual pattern.

---

## 2026-08-01 — Yeruham Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `yeruham` (`handasa.yeroham.muni.il/binyan/#taba/307`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 49 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-08-01 — Yavne Complot link override

- Added an eleventh Complot frontend-link template (`_YAVNE_LINK` in
  `run_committee_sweep.py`): `/taba2/`, keyed by plan number via `GetTabaByNumber` like
  `bnei brak`/`givatayim`/`hod hasharon`. Registered for `"yavne"`. Backfilled all 67
  existing rows in `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-08-01 — Tzefat registry fix + full Complot site_id verification sweep

- Re-opened the Tzefat/Emek HaYarden finding from 2026-07-31 (previously misjudged as
  "not a bug") after pulling all 79 `committee_state.db` rows tagged `muni='tzefat'` and
  finding every one was genuinely Jordan Valley content, one literally titled "תכנית
  אסטרטגית למרחב תכנון עמק הירדן." Confirmed Complot site_id 12 truly belongs to Emek
  HaYarden (its own domain declares that value itself, independent of the registry).
- Ran a full probe of all 69 Complot-system registry entries in
  `local_committee_scrapers` — fetched each municipality's own domain and read the
  `var site_id = N` its real plan-search widget declares (static HTML string, no browser
  needed). Learned that several municipalities' `/binyan/` pages are uncustomized
  copy-pasted demo content showing a different real client's site_id verbatim, which
  would have produced false-positive "fixes" if trusted blindly. After the user
  independently verified each flagged case against real `GetTabaByAuthority`/
  `GetBakashotByInterestedParty` search URLs on each site, only Tzefat's registry entry
  was actually wrong; `hagalil lower`, `ganei tikva`, `yavne`, `nazareth`,
  `menashe alona`, `nahariya`, `yoqne'am illit`, `bnei brak`, `givatayim`, and `ariel`
  were all already correct.
- **Fix**: corrected `dispatcher.py`'s `"tzefat"` site_id (12 -> 88, user-confirmed).
  Retagged 76 `committee_state.db` rows from `tzefat` to `emeq hayarden` (3 were already
  duplicates there), reset `tzefat`'s scrape timestamp, regenerated `mavat_review.html`
  (21,701 open candidates).

---

## 2026-07-31 — Tira/Hagalil Center site_id collision fixed

- Found (user report: "many showing tira but being in the north") and confirmed a
  site_id collision in `local_committee_scrapers`'s own registry: `"tira"` and
  `"hagalil center"` were both registered with `site_id: 20`, so every "tira" scrape was
  actually re-fetching Hagalil Center's backend under the wrong label — all 240
  `committee_state.db` rows tagged `muni='tira'` were exact plan-number duplicates of the
  240 correct `hagalil center` rows.
  - Deleted the 240 duplicate rows and reset `tira`'s `last_scraped_at` in this project's
    `committee_state.db`; regenerated `mavat_review.html`.
  - User found Tira's real site_id (24) and it's now corrected in
    `local_committee_scrapers/unified_scraper/municipal_scraper/registry/dispatcher.py`.
    Tira will scrape its own real data on its next rotation turn.
  - Also checked plan `214-0907980` (Tzefat vs. Emek HaYarden) — not a bug, different
    root cause (Tzefat's own site_id correctly matches; likely inter-municipal committee
    jurisdiction, not a data error). See `docs/BUG_REFERENCE.md` for detail.

---

## 2026-07-30 — Tiberias Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `tiberias` (`tiberias.complot.co.il/binyan/#taba/2046`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 81 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Sdot Dan Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `sdot dan` (`sdan.complot.co.il/binyan/#taba/1850`); added to the `iron`-pattern batch
  list in `run_committee_sweep.py`. Backfilled all 96 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Sderot Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for `sderot`
  (`sderot.complot.co.il/binyan/#taba/19264`); added to the `iron`-pattern batch list in
  `run_committee_sweep.py`. Backfilled all 68 existing rows in `committee_state.db` and
  regenerated `mavat_review.html`.

---

## 2026-07-30 — Saronim Complot link override

- Confirmed Saronim reuses the existing `kfar saba`/`ofaqim`/`qiryat gat`/`ramat hasharon`
  template (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `www.sharonim.org.il/newengine/Pages/taba2.aspx#taba/5953`. Registered `"saronim"` in
  `COMPLOT_MUNI_LINK_OVERRIDES` (no new lambda). Backfilled all 96 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Rishon LeZion Complot link override

- Added a tenth Complot frontend-link template (`_RISHON_LEZION_LINK` in
  `run_committee_sweep.py`): same `taba2.aspx` page as `kfar saba`, but on the
  municipality's own domain (`www.rishonlezion.muni.il`) rather than the registry's
  `rishonlezion.complot.co.il` — a hardcoded-domain override like `givatayim`.
  Registered for `"rishon lezion"`. Backfilled all 589 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Rehovot Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `rechovot` (`rechovot.complot.co.il/binyan/#taba/5443`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 252 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Ramat Hasharon Complot link override

- Confirmed Ramat Hasharon reuses the existing `kfar saba`/`ofaqim`/`qiryat gat` template
  (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `ramathasharon.complot.co.il/newengine/pages/taba2.aspx#taba/3164`. Registered
  `"ramat hasharon"` in `COMPLOT_MUNI_LINK_OVERRIDES` (no new lambda). Backfilled all 240
  existing rows in `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Ramat Gan Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `ramat gan` (`handasa.ramat-gan.muni.il/binyan/#taba/4207`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 146 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Rahat Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for `rahat`
  (`rahat.complot.co.il/binyan/#taba/1440`); added to the `iron`-pattern batch list in
  `run_committee_sweep.py`. Backfilled all 158 existing rows in `committee_state.db` and
  regenerated `mavat_review.html`.

---

## 2026-07-30 — Raanana Complot link override

- Added a ninth Complot frontend-link template (`_RAANANA_LINK` in
  `run_committee_sweep.py`): keyed by internal id via `#taba/<n>` like
  `iron`/`nahariya`/`petah tikva`, but on the municipality's own domain at
  `/residents/engineering/planning-information/tba/#taba/<n>`. Registered for
  `"raanana"`. Backfilled all 34 existing rows in `committee_state.db` and regenerated
  `mavat_review.html`.

---

## 2026-07-30 — Qiryat Malakhi Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `qiryat malakhi` (`km.complot.co.il/binyan/#taba/3808`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 24 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-30 — Qiryat Gat Complot link override

- Confirmed Qiryat Gat reuses the existing `kfar saba`/`ofaqim` template
  (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `qiryat-gat.complot.co.il/newengine/Pages/taba2.aspx#taba/100634`. Registered
  `"qiryat gat"` in `COMPLOT_MUNI_LINK_OVERRIDES` (no new lambda). Backfilled all 119
  existing rows in `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-29 — Petah Tikva Complot link override

- Added an eighth Complot frontend-link template (`_PETAH_TIKVA_LINK` in
  `run_committee_sweep.py`): keyed by internal id via `#taba/<n>` like `iron`/`nahariya`,
  but on the municipality's own domain at
  `/engineering/planning-and-building/taba2#taba/<n>`. Registered for `"petah tikva"`.
  Backfilled 349 of 383 existing rows in `committee_state.db` (34 had no backend link to
  begin with) and regenerated `mavat_review.html`.

---

## 2026-07-28 — Or Yehuda Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `or yehuda` (`oryehuda.complot.co.il/binyan/#taba/836`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 28 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-28 — Ofaqim Complot link override

- Confirmed Ofaqim reuses the existing `kfar saba` template
  (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `ofaqim.complot.co.il/newengine/Pages/taba2.aspx#taba/839`. Registered `"ofaqim"` in
  `COMPLOT_MUNI_LINK_OVERRIDES` (no new lambda). Backfilled all 131 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-26 — Nahariya Complot link override

- Added a seventh Complot frontend-link template (`_NAHARIYA_LINK` in
  `run_committee_sweep.py`): keyed by internal id via `#taba/<n>` like `iron`, but on the
  municipality's own domain with a Hebrew path segment (`/תכניות-בנין-עיר/`) instead of
  `iron`'s `/binyan/`. Registered for `"nahariya"`. Backfilled all 73 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-26 — Mordot Carmel Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for
  `mordot carmel` (`www.mordotcarmel.org/binyan/#taba/1822`); added to the `iron`-pattern
  batch list in `run_committee_sweep.py`. Backfilled all 94 existing rows in
  `committee_state.db` and regenerated `mavat_review.html`.

---

## 2026-07-22 — Modi'in Complot link override

- Confirmed the `iron` frontend-link pattern (`/binyan/#taba/<internal-id>`) for `modi'in`
  (`modiin.complot.co.il/binyan/#taba/4362`); added to the `iron`-pattern batch list in
  `run_committee_sweep.py`. Backfilled all 213 existing rows in `committee_state.db` and
  regenerated `mavat_review.html`.

---

## 2026-07-22 — Migdal Ha'emeq Complot link override

- Added a sixth Complot frontend-link template (`_MIGDAL_HAEMEQ_LINK` in
  `run_committee_sweep.py`): `iron`'s `/binyan/` page path, but keyed by plan number via
  `GetTabaByNumber` like `bnei brak`/`givatayim`/`hod hasharon`. Registered for
  `"migdal ha'emeq"`. Backfilled all 64 existing rows in `committee_state.db` and
  regenerated `mavat_review.html` (14,513 open candidates).

---

## 2026-07-22 — R6 regional-council blocklist, energy-rule regex fix

- **R6 (new, committee-only)**: unconditional auto-exclusion for 18 regional councils
  (`BLOCKED_COMMITTEE_MUNIS` in `auto_rules.py`) where the user has rejected every
  candidate ever surfaced — thousands of rows, 0 kept. Found by analyzing
  `docs/mavat_review_decisions (6).json` (11,905 decisions): these councils cover
  dispersed rural kibbutzim/moshavim, and their filings are almost always internal
  mechanics (parceling, adding a 3rd unit to one farm plot, internal zoning) rather than
  real neighborhood development. Deliberately has no content override (unlike every other
  rule) — testing showed 331 already-excluded plans in these same councils already
  contained a nominal "positive signal" keyword (שכונ/תוספת יח"ד/מתחם) and were rejected
  anyway. `mitar` was evaluated and explicitly excluded from the blocklist: it has a
  genuine open neighborhood candidate (`652-0754705`, "חורה - שכונה 27", in the Bedouin
  town of Hura). Applied once: 1,464 committee candidates auto-excluded.
- **ENERGY_RULE regex broadened** to also catch `אגרו וולטאי` (agro-voltaic), not just
  `פוטו.?וולט` (photo-voltaic) — see `docs/BUG_REFERENCE.md`. 7 mavat + 3 committee
  candidates caught on the same run.

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
