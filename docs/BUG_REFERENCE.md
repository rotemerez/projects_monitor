# Bug Reference

**Last Updated:** 2026-07-31

Known issues, root causes, and solutions. Newest on top.

---

## Tira/Hagalil Center site_id collision — Tira never actually scraped (FIXED 2026-07-31)
- **Symptom**: 240 committee candidates tagged `muni='tira'` in `committee_state.db` were
  all Western Galilee content (אבו סנאן, ירכא, ג'וליס, כפר יאסיף — Hagalil Center
  territory, plan-number prefix `252`), not Tira (the Triangle-area Arab town, central
  district). User spotted "many showing tira but being in the north."
- **Root cause**: upstream in `local_committee_scrapers`'s own
  `registry/dispatcher.py` — both `"hagalil center"` (`galil-merkazi.co.il`) and
  `"tira"` (`tira1.complot.co.il`) are registered with the identical `site_id: 20`.
  Confirmed by exact-match: all 240 "tira" rows are plan-number-for-plan-number
  duplicates of the 240 already-correct "hagalil center" rows — Tira has apparently
  never actually been scraped; every "tira" run just re-fetches Hagalil Center's
  backend under the wrong label.
- **Fix so far (this project only)**: deleted the 240 duplicate `tira` rows from
  `committee_state.db` (safe — Hagalil Center's correct data is untouched under its own
  muni key) and reset `tira`'s `last_scraped_at` so it re-scrapes fresh once corrected.
  Regenerated `mavat_review.html`.
- **Registry fix**: user found Tira's real site_id (**24**, confirmed via
  `tira1.complot.co.il/newengine/Pages/meetings2.aspx#search/GetMeetingByDate&siteid=24`).
  Corrected `local_committee_scrapers/unified_scraper/municipal_scraper/registry/
  dispatcher.py:133` (`"tira"` entry's `site_id`: 20 -> 24). Tira will now scrape its own
  real data on its next rotation turn instead of re-fetching Hagalil Center's.
- **Not yet added**: a Complot frontend-link override for `"tira"` in this project's own
  `run_committee_sweep.py` (`COMPLOT_MUNI_LINK_OVERRIDES`) — the homepage links to
  `/newengine/Pages/taba2.aspx` (same page as the `kfar saba` family), but per this file's
  own rule, an override needs a confirmed working `#taba/<n>`-style example before being
  added, not just the page path. Add once a real plan link pair is available.

### Tzefat registry entry actually served Emek HaYarden's data (FIXED 2026-08-01)
- **Symptom**: plan `214-0907980` (מגרש 38 - אלומות) showed מיקום=Tzefat despite Alumot
  being in the Jordan Valley (Emek HaYarden). Initially assessed as "not a bug" (see
  history below) since the plan's own `siteid=12` matched Tzefat's then-registered value
  with no numeric collision like the Tira case. That assessment was wrong.
- **Root cause found on deeper check**: pulled the full list of all 79 rows tagged
  `muni='tzefat'` in `committee_state.db` — every single one was Jordan Valley content
  (כנרת, אפיקים, דגניה, פוריה, אשדות יעקב, אלומות, מעגן, עין גב, צמח, גינוסר), one
  literally titled **"תכנית אסטרטגית למרחב תכנון עמק הירדן"**. Tzefat's registry entry
  (site_id 12) was simply wrong — Complot's site_id 12 genuinely belongs to Emek
  HaYarden (independently confirmed: `emekhayarden.complot.co.il`'s own plan-search page
  declares `site_id=12` itself, with CSS client code `EMY` and a self-consistent
  Google Analytics ID). Tzefat's real data has never been correctly scraped.
- **Systemic follow-up**: this prompted a full probe of all 69 Complot-system registry
  entries (fetch each municipality's own domain, extract the `var site_id = N` its plan-
  search widget's embedded `<script>` declares, no browser/JS execution needed — it's a
  static string). Found that many municipalities' `/binyan/` pages are an uncustomized,
  copy-pasted WordPress/Elementor demo snippet showing a **different, unrelated real
  client's** site_id verbatim (e.g. several showed Emek HaYarden's own values, one showed
  Taibeh's, one showed Bat Yam's) — a trap for naive automated "just read the first
  site_id you find" probing. After separating genuine unedited duplicates from
  coincidental shared-theme false alarms (cross-checked with the user against each
  site's own real `GetTabaByAuthority`/`GetBakashotByInterestedParty` search URLs), only
  **Tzefat's registry entry was actually wrong** — every other checked entry
  (`hagalil lower`, `ganei tikva`, `yavne`, `nazareth`, `menashe alona`, `nahariya`,
  `yoqne'am illit`, `bnei brak`, `givatayim`, `ariel`) was already correct.
- **Fix**: user found Tzefat's real site_id (**88**, confirmed via
  `zefat.complot.co.il/request/#search/GetBakashotByInterestedParty&siteid=88`).
  Corrected `local_committee_scrapers/.../registry/dispatcher.py` (`"tzefat"` site_id:
  12 -> 88). In this project's `committee_state.db`: retagged the 76 non-duplicate
  `tzefat` rows to `emeq hayarden` (their genuine content; 3 were already exact
  duplicates there and got dropped), reset `tzefat`'s `last_scraped_at` so it scrapes
  fresh with its real site_id, and regenerated `mavat_review.html`.

---

## Committee scraper — Complot frontend link rewriting (cont'd)

### Yeruham had no link override, showed raw backend URL (FIXED 2026-08-01)
- **Symptom**: Yeruham's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works:
  `handasa.yeroham.muni.il/binyan/#taba/307`.
- **Fix**: added `"yeruham"` to the `iron`-pattern batch list. Backfilled all 49 existing
  rows in `committee_state.db`.

### Yavne had no link override, showed raw backend URL (FIXED 2026-08-01)
- **Symptom**: Yavne's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: an eleventh distinct template — `/taba2/` (not the
  `/newengine/Pages/taba2.aspx` family), keyed by plan number via `GetTabaByNumber` like
  `bnei brak`/`givatayim`/`hod hasharon`. Confirmed by user:
  `yavne.complot.co.il/taba2/#search/GetTabaByNumber&siteid=87&n=404-0506931&l=true&arguments=siteid,n,l`.
- **Fix**: added `_YAVNE_LINK` override, registered for `"yavne"`. Backfilled all 67
  existing rows in `committee_state.db`.

### Tiberias had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Tiberias's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works:
  `tiberias.complot.co.il/binyan/#taba/2046`.
- **Fix**: added `"tiberias"` to the `iron`-pattern batch list. Backfilled all 81 existing
  rows in `committee_state.db`.

### Sdot Dan had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Sdot Dan's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `sdan.complot.co.il/binyan/#taba/1850`.
- **Fix**: added `"sdot dan"` to the `iron`-pattern batch list. Backfilled all 96 existing
  rows in `committee_state.db`.

### Sderot had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Sderot's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works:
  `sderot.complot.co.il/binyan/#taba/19264`.
- **Fix**: added `"sderot"` to the `iron`-pattern batch list. Backfilled all 68 existing
  rows in `committee_state.db`.

### Saronim had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Saronim's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed it reuses the
  existing `kfar saba`/`ofaqim`/`qiryat gat`/`ramat hasharon` template
  (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `www.sharonim.org.il/newengine/Pages/taba2.aspx#taba/5953`.
- **Fix**: registered `"saronim"` -> `_KFAR_SABA_LINK` (no new lambda needed).
  Backfilled all 96 existing rows in `committee_state.db`.

### Rishon LeZion had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Rishon LeZion's plan links in `mavat_review.html` pointed at the raw
  backend viewer instead of the municipality's own frontend.
- **Root cause**: a tenth distinct template — same `taba2.aspx` page as `kfar saba`, but
  served from the municipality's own domain (`www.rishonlezion.muni.il`) rather than the
  registry's `rishonlezion.complot.co.il` (a `base`-ignoring hardcoded-domain override,
  like `givatayim`). Confirmed by user: `www.rishonlezion.muni.il/Residents/Construction/
  newengine/Pages/taba2.aspx#taba/14903`.
- **Fix**: added `_RISHON_LEZION_LINK` override, registered for `"rishon lezion"`.
  Backfilled all 589 existing rows in `committee_state.db`.

### Rehovot had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Rehovot's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works:
  `rechovot.complot.co.il/binyan/#taba/5443`.
- **Fix**: added `"rechovot"` to the `iron`-pattern batch list. Backfilled all 252
  existing rows in `committee_state.db`.

### Ramat Hasharon had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Ramat Hasharon's plan links in `mavat_review.html` pointed at the raw
  backend viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed it reuses the
  existing `kfar saba`/`ofaqim`/`qiryat gat` template
  (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `ramathasharon.complot.co.il/newengine/pages/taba2.aspx#taba/3164`.
- **Fix**: registered `"ramat hasharon"` -> `_KFAR_SABA_LINK` (no new lambda needed).
  Backfilled all 240 existing rows in `committee_state.db`.

### Ramat Gan had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Ramat Gan's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works:
  `handasa.ramat-gan.muni.il/binyan/#taba/4207`.
- **Fix**: added `"ramat gan"` to the `iron`-pattern batch list. Backfilled all 146
  existing rows in `committee_state.db`.

### Rahat had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Rahat's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `rahat.complot.co.il/binyan/#taba/1440`.
- **Fix**: added `"rahat"` to the `iron`-pattern batch list. Backfilled all 158 existing
  rows in `committee_state.db`.

### Raanana had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Raanana's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: a ninth distinct template — keyed by internal id via `#taba/<n>` like
  `iron`/`nahariya`/`petah tikva`, but yet another own-domain page path. Confirmed by
  user: `www.raanana.muni.il/residents/engineering/planning-information/tba/#taba/5606`.
- **Fix**: added `_RAANANA_LINK` override, registered for `"raanana"`. Backfilled all 34
  existing rows in `committee_state.db`.

### Qiryat Malakhi had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Qiryat Malakhi's plan links in `mavat_review.html` pointed at the raw
  backend viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `km.complot.co.il/binyan/#taba/3808`.
- **Fix**: added `"qiryat malakhi"` to the `iron`-pattern batch list. Backfilled all 24
  existing rows in `committee_state.db`.

### Qiryat Gat had no link override, showed raw backend URL (FIXED 2026-07-30)
- **Symptom**: Qiryat Gat's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed it reuses the
  existing `kfar saba`/`ofaqim` template (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `qiryat-gat.complot.co.il/newengine/Pages/taba2.aspx#taba/100634`.
- **Fix**: registered `"qiryat gat"` -> `_KFAR_SABA_LINK` (no new lambda needed).
  Backfilled all 119 existing rows in `committee_state.db`.

### Petah Tikva had no link override, showed raw backend URL (FIXED 2026-07-29)
- **Symptom**: Petah Tikva's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: an eighth distinct template — keyed by internal id via `#taba/<n>` like
  `iron`/`nahariya`, but yet another own-domain page path. Confirmed by user:
  `www.petah-tikva.muni.il/engineering/planning-and-building/taba2#taba/8106`.
- **Fix**: added `_PETAH_TIKVA_LINK` override, registered for `"petah tikva"`. Backfilled
  349 of 383 existing rows in `committee_state.db` (the other 34 had no backend link
  populated to begin with — left as-is).

### Or Yehuda had no link override, showed raw backend URL (FIXED 2026-07-28)
- **Symptom**: Or Yehuda's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `oryehuda.complot.co.il/binyan/#taba/836`.
- **Fix**: added `"or yehuda"` to the `iron`-pattern batch list. Backfilled all 28
  existing rows in `committee_state.db`.

### Ofaqim had no link override, showed raw backend URL (FIXED 2026-07-28)
- **Symptom**: Ofaqim's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed it reuses the
  existing `kfar saba` template (`/newengine/Pages/taba2.aspx#taba/<internal-id>`):
  `ofaqim.complot.co.il/newengine/Pages/taba2.aspx#taba/839`.
- **Fix**: registered `"ofaqim"` -> `_KFAR_SABA_LINK` (no new lambda needed). Backfilled
  all 131 existing rows in `committee_state.db`.

### Nahariya had no link override, showed raw backend URL (FIXED 2026-07-26)
- **Symptom**: Nahariya's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: a seventh distinct template — keyed by internal id via `#taba/<n>`
  like `iron`, but a different page path: own municipal domain with a Hebrew path segment
  (`/תכניות-בנין-עיר/`) rather than `iron`'s `/binyan/`. Confirmed by user:
  `www.nahariya.muni.il/תכניות-בנין-עיר/#taba/1291`.
- **Fix**: added `_NAHARIYA_LINK` override, registered for `"nahariya"`. Backfilled all 73
  existing rows in `committee_state.db`.

### Mordot Carmel had no link override, showed raw backend URL (FIXED 2026-07-26)
- **Symptom**: Mordot Carmel's plan links in `mavat_review.html` pointed at the raw
  backend viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `www.mordotcarmel.org/binyan/#taba/1822`.
- **Fix**: added `"mordot carmel"` to the `iron`-pattern batch list. Backfilled all 94
  existing rows in `committee_state.db`.

### Modi'in had no link override, showed raw backend URL (FIXED 2026-07-22)
- **Symptom**: Modi'in's plan links in `mavat_review.html` pointed at the raw backend
  viewer instead of the municipality's own frontend.
- **Root cause**: no entry in `COMPLOT_MUNI_LINK_OVERRIDES`. User confirmed the `iron`
  pattern (`/binyan/#taba/<internal-id>`) works: `modiin.complot.co.il/binyan/#taba/4362`.
- **Fix**: added `"modi'in"` to the `iron`-pattern batch list. Backfilled all 213 existing
  rows in `committee_state.db`.

### Migdal Ha'emeq had no link override, showed raw backend URL (FIXED 2026-07-22)
- **Symptom**: Migdal Ha'emeq's plan links in `mavat_review.html` pointed at the ugly,
  low-graphics backend viewer (`handasi.complot.co.il/magicscripts/mgrqispi.dll?...`)
  instead of the municipality's own frontend, since it had no entry in
  `COMPLOT_MUNI_LINK_OVERRIDES` (`run_committee_sweep.py`).
- **Root cause**: a sixth distinct Complot frontend template — same `/binyan/` page path
  as the `iron` pattern, but keyed by plan **number** via `GetTabaByNumber` (like
  `bnei brak`/`givatayim`/`hod hasharon`), not `iron`'s `#taba/<internal-id>`. Confirmed
  by user: `migdal-haemeq.complot.co.il/binyan/#search/GetTabaByNumber&siteid=8&n=221-1051697&l=true&arguments=siteid,n,l`.
- **Fix**: added `_MIGDAL_HAEMEQ_LINK` override, registered for `"migdal ha'emeq"`.
  Backfilled all 64 existing rows in `committee_state.db` (new rows self-correct on
  scrape; overrides only apply at import time, not retroactively).

---

## Mavat scraper — discovery/review pipeline (cont'd, 2)

### ENERGY_RULE missed agro-voltaic phrasing (FIXED 2026-07-22)
- **Symptom**: `206-1183003` ("מתקן אגרו וולטאי בשטחי כפר חיטים") was manually rejected
  ("not interested in photo voltaic fields") instead of being auto-excluded.
- **Root cause**: `auto_rules.py`'s `ENERGY_RULE` regex only matched `פוטו.?וולט`
  (photo-voltaic); the equally common `אגרו וולטאי` (agro-voltaic — solar panels installed
  over active farmland) phrasing wasn't covered.
- **Fix**: broadened to `(פוטו|אגרו).?וולט`.

---

## Mavat scraper — discovery/review pipeline (cont'd)

### R3 auto-exclusion fired on unconfirmed default unit count (FIXED 2026-07-21)
- **Symptom**: `416-1448794` (real units=15) got auto-excluded by `auto_rules.py`'s R3 on
  its very first day in the discovery queue.
- **Root cause**: every newly discovered row defaults to `units_ge10=0` until
  `mavat_discover_units.py` fetches a real count; R3 treated that placeholder as
  equivalent to a real confirmed low count and excluded the plan before it ever got a
  chance to be checked.
- **Fix**: R3 now requires `confirmed=True` (set only once a real fetch has happened) —
  an unconfirmed low `units_ge10` flag does nothing; the plan stays open until confirmed
  one way or the other.

### Stale browser-cache kept an un-excluded plan showing "excluded" (FIXED 2026-07-21)
- **Symptom**: `502-1406529` was auto-excluded, then un-excluded server-side (same-day
  rule fix + backlog reopen), but an already-open browser tab kept showing it as excluded.
- **Root cause**: `mavat_review.html`'s `localStorage`-seeding logic only ever seeded a
  plan's decision once per browser; a later server-side change to an auto-tagged decision
  was never picked back up.
- **Fix**: only decisions whose reason starts `אוטומטי:` (auto-rule origin) now re-sync
  from the DB on every page load to match current server state; any genuine human decision
  is left untouched.

### Silent near-empty vault read produced a missed status change (FIXED 2026-07-19)
- **Symptom**: a real status change on `414-1294818` went undetected by a scheduled run.
- **Root cause**: `mavat_diff.py` read `projects.db` while it was mid-rebuild (a
  scheduled-task pile-up window, e.g. after the machine woke from sleep), got back a
  truncated table, and silently ran its diff against a near-empty plan list instead of
  failing loudly.
- **Fix**: `load_tracked_plans()` returning fewer than 1000 plans (vs. the normal several
  thousand) now hard-fails the run instead of proceeding.

---

## Mavat scraper — discovery/review pipeline

### `status_date`/`decision_date` field mapping was swapped (FIXED 2026-07-16)
- **Symptom**: 4 of 5 pending `שינויי סטטוס לאישור` entries showed the *same* status text
  before and after, only the date differed — looked like noise, not real changes. Also, a
  live screenshot of a plan's own Mavat page showed a different date next to its current
  status than what the pipeline had recorded.
- **Root cause**: `mavat_status.py`'s `_extract()` mapped `status_date` from
  `INTERNET_STATUS_DATE` and `decision_date` from `BI_STATUS_DATE` — backwards.
  `BI_STATUS_DATE` is the date actually shown next to the current status on the plan's own
  page; `INTERNET_STATUS_DATE` instead tracks the latest entry across the *whole* "שלבי
  טיפול בתכנית" stage-history table, which can advance from an unrelated administrative
  sub-step (e.g. a Treasury sub-approval) without the real status or its date moving at
  all. Using it as "status_date" made `mavat_diff.py`'s change-detection
  (`status_date != old_date`) fire on pure noise.
- **Fix**: swapped the mapping in `mavat_status.py` (`_extract()`) and
  `mavat_discover.py`'s inline extraction. Backfilled all 2,029 `mavat_state.db` rows for
  free (both fields were already stored, just swapped the two columns — no re-scraping
  needed). `mavat_discovery.db`'s `status_date` self-corrects as rows get naturally
  re-touched by future incremental sweeps (no backfill there — not worth a live re-scrape
  for a display date).
- **Fallout**: the 4 same-status pending changes were confirmed false positives from this
  bug and dismissed (`353-1545854`, `306-1464056`, `302-1306018`, `215-1288927`); the 1
  genuine transition (`216-1534395`, `בבדיקה תכנונית → נדחתה`) was kept for normal review.

### SQL `NOT LIKE` against a nullable column silently hid every open candidate (FIXED 2026-07-16)
- **Symptom**: the daily discovery run reported very few plans for review; a specific plan
  known to have changed status the day before (`102-1477827`) was completely absent from
  `mavat_review.html`, even though its DB row was correct (`excluded=0`, target status).
- **Root cause**: a filter added to `make_review_page.py`'s candidate query
  (`AND exclude_reason NOT LIKE 'אוטומטי: סטטוס נכלל לראשונה%'`, meant to strip a
  one-time migration-noise tag out of the payload) evaluates to SQL `NULL` — not
  `TRUE` — for every row where `exclude_reason IS NULL`. A `WHERE` clause treats `NULL` as
  false, so **every genuinely open, never-excluded candidate** (all of which have
  `exclude_reason IS NULL`) was silently dropped from the page. Not just the intended
  migration noise — everything.
- **Fix**: `(exclude_reason IS NULL OR exclude_reason NOT LIKE '...')`. **Lesson: any
  future `NOT LIKE`/`!=`/`<>` filter against a nullable column needs the same `IS NULL OR`
  guard** — SQL NULL comparisons never evaluate to true, including negated ones.

---

## Mavat scraper

### Batch runs produced mostly FALSE misses: 'כל התכניות' click silently failing (FIXED 2026-07-08)
- **Symptom**: a 30-plan batch run returned 10 misses out of 11 new plans; the same "missed"
  plans matched fine when probed individually. Misses clustered on plans without recent
  committee activity.
- **Root cause**: the "כל התכניות" (all plans) click used `timeout=3000` and swallowed the
  TimeoutError. When the SPA rendered slowly (common mid-batch), the click failed silently and
  the search POST went out with the **default last-3-months filter**, hiding any plan not
  discussed recently → false MISS. Confirmed by capturing the `sv3/Search` request payload:
  failed-click lookups sent `internetStatus:{CODE:"-1"}`-style default-filter payloads.
- **Fix**: `_select_all_plans()` clicks and then **verifies** the radio is checked
  (`get_by_role("radio").first.is_checked()` — the radios are custom ARIA components, NOT
  `<input>` elements, so an `input[...]` selector never matches). If the filter can't be
  verified within 15s the lookup returns `error=filter_not_set` instead of a false miss, and
  `mavat_diff.py` leaves the plan for the next rotation rather than recording anything.
- **Verified**: the exact 8-lookup sequence that produced 3 false misses now matches 8/8.

### Intermittent / concurrent MISS: generic searches falsely ended the result wait (FIXED 2026-07-08)
- **Symptom**: sequential lookups occasionally returned MISS for a plan that exists (matched on
  immediate re-run); under 3 parallel contexts nearly every lookup missed, with zero non-200s.
- **Root cause**: the SV3 page fires its own generic `sv3/Search` requests — one on page load
  and one when clicking the "כל התכניות" filter. The wait loop counted *any* new search
  response as "our query returned," so a late-arriving generic response (or, in `conc_test.py`,
  the page-load response — its baseline was taken *before* `goto`) ended the wait before the
  plan's real result arrived → false MISS. Sequential runs usually won the race; under
  concurrency the site slows and loses it.
- **Fix** (both `mavat_status.py` and `conc_test.py`): identify OUR search response by its
  request payload (`resp.request.post_data` contains the plan number); loop until an exact
  ENTITY_NUMBER match appears or the plan-specific response proves a genuine miss.
- **Verified**: 3 workers × 5 plans now fully consistent (same OK/MISS per plan on all
  workers), 0 WAF blocks; warm hit 7–9s sequential, ~5s effective at concurrency 3.

### Hebrew output crashes with `UnicodeEncodeError: cp1252`
- **Symptom**: script dies at the first `print()` of Hebrew text on Windows.
- **Root cause**: Windows console default encoding is cp1252, which can't encode Hebrew.
- **Fix**: run with `python -X utf8` or set `$env:PYTHONUTF8=1`; scripts also call
  `sys.stdout.reconfigure(encoding="utf-8")` defensively.

### Plan-number field not found / not visible (`wait_for_selector` timeout)
- **Root cause**: the plan-number `<input>`'s `id` attribute contains a space
  (`program-number-plans-1 plan-program-number`), so `#program-number-plans-1` never matches.
  Some loads also render it inside a collapsed panel.
- **Fix**: select by the stable aria-label — `input[aria-label='מספר תכנית']` — and
  `wait_for(state="visible")`.

### False "not found" for older plans
- **Root cause**: the search defaults to a "תכניות שנדונו בטווח של 3 חודשים" (last-3-months)
  radio, which hides plans not discussed recently.
- **Fix**: click "כל התכניות" (all plans) before submitting.

### A missing plan hung the lookup for ~39s
- **Root cause**: the wait loop had no way to tell "search returned, no match" from "results
  not in yet," so it ran to the full timeout.
- **Fix**: track the count of `sv3/Search` responses; once a *new* (post-submit) response
  arrives, extract immediately — match or genuine miss returns in ~6s.

### In-page `fetch('/rest/api/SV4/1?mid=...')` returns the 404 WAF page
- **Root cause**: the WAF/server distinguishes the SPA's own XHR (right referer/sec-fetch/guid)
  from an injected `fetch`, even from a warmed page.
- **Workaround**: don't call the REST endpoint directly; drive the search UI and read the
  `sv3/Search` response (which has status + code + date anyway).

### All-miss + a 401 under parallel contexts (RESOLVED 2026-07-08)
- **Symptom**: `conc_test.py` at concurrency 3 returned all misses and one 401 on `sv3/Search`.
- **Causes (two stacked test bugs, not WAF)**: (1) the async route handler was fire-and-forget
  (`lambda r: asyncio.create_task(...)`), breaking request interception — fixed earlier;
  (2) the response baseline was captured before `goto`, so the page-load's own generic search
  satisfied the wait — see "generic searches falsely ended the result wait" above.
- **Conclusion after clean re-run**: concurrency 3 works — results fully consistent across
  workers, 0 non-200 responses. No WAF pushback observed at this level.

---

## Investigation notes (not code bugs)

### "DB has only one table" — was a sqlite-cursor inspection bug
- **What happened**: an early inspection script reused a single sqlite cursor to run
  `count(*)` inside a loop over `sqlite_master`, which truncated the outer iteration after the
  first table — making it look like `projects.db` had only the `projects` table.
- **Reality**: `projects.db` has all five tables (`projects`, `status_events`, `tenders`,
  `signatures`, `value_history`), built by `scripts/refresh_db.py`. Verified 2026-07-08 by
  fetching rows into memory instead of reusing the cursor.
- **Lesson**: use a separate cursor (or `fetchall()`) when querying inside a cursor loop.
