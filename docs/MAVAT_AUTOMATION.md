# External data sources for plan tracking — findings

_Companion to `framework_spec.md` / `HANDOFF.md`. Goal: identify an available feed/API from מנהל התכנון (Israel Planning Administration) for looking up a plan by plan number (`plan_current`), as a prerequisite before building the pull+diff pipeline._

## Summary — update after live browser test
Confirmed with a real browser session (Claude in Chrome) against plan `457-1253954`: Mavat works and returns exactly the data we need — current status, date, unit/area counts, and a full committee-meeting history (dates + institution + status per meeting, i.e. our `status_events` equivalent).

**Important architectural finding (confirmed, not just suspected):** the Mavat REST endpoint (`mavat.iplan.gov.il/rest/api/SV4/1?mid=...`) and the Xplan ArcGIS endpoint both return data fine through the real Chrome browser, but are blocked for plain scripts — **and this is not geographic**. We tested directly from an Israeli IP (the user's own machine) with curl/PowerShell:
- A bare `curl`/`Invoke-RestMethod` call to either endpoint returns a gov.il WAF "page not found" error page, not real data.
- Loading the page first to capture session cookies, then replaying the API call with those cookies + a `Referer` + `X-Requested-With` header, **still** failed with a (different) WAF error page.
- The cookie curl received (`TS01f22d23...`) is a classic F5/anti-bot "TS" challenge cookie — these typically require actual in-browser JavaScript execution (fingerprinting/challenge-response) to validate, which curl/`requests`/PowerShell cannot do.

**Conclusion: this is bot/WAF protection, not geo-blocking or a simple auth/header requirement.** Plain server-side HTTP calls (curl, Python `requests`, etc.) cannot reach either API, even from an Israeli IP with correct headers and a valid session cookie. **The daily pipeline must drive an actual browser (Claude in Chrome, or a full JS-capable automated browser like Playwright/Puppeteer) rather than call these endpoints directly from a script.**

## Sources checked

### 1. Mavat — planning information site (mavat.iplan.gov.il) — leading candidate
- This is the Planning Administration's official site for searching plans/requests/appeals by plan number, name, entity type, etc. Public, free (gov.il: "Locating plans, meetings and appeals").
- Entry URL: `https://mavat.iplan.gov.il/SV3` (search), e.g. `SV3?searchEntity=1&entityType=1&searchMethod=2` for plan search.
- **Found a hint of an internal API:** a path `mavat.iplan.gov.il/rest/api/Attacments/?eid=...&fn=...` exists (used for downloading an attachment) — meaning there's a REST server behind the site, but no public documentation for it was found.
- **Verified working (Claude in Chrome, live test):** navigated to `mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1&searchMethod=2` (advanced plan search), entered plan number `457-1253954` in the "מספר תכנית" field, pressed Enter. The SPA redirected to `https://mavat.iplan.gov.il/SV4/1/4005328820/310` (`4005328820` = the plan's internal `mid`) and rendered:
  - Current status + date: **אישור (approved), 28/06/2026**
  - Units: 364 (יח"ד), area: 17,082 sqm gross / 3,600 sqm public buildings (מבני ציבור)
  - A full **committee decision history** table (מוסד תכנון / meeting date / meeting status / meeting number) — this maps directly onto our `status_events` table.
- The underlying call captured in the Network panel was `GET https://mavat.iplan.gov.il/rest/api/SV4/1?mid=4005328820&guid=0`. The plan-number → `mid` resolution itself happens client-side inside the SPA (likely a cached/typeahead index) and wasn't captured as a separate visible network request.
- **Caveat (confirmed via local test from Israel):** this REST endpoint is behind WAF/bot-detection (F5-style "TS" challenge cookie) — a bare curl call, and even curl with a valid session cookie + Referer + XHR header, both got a WAF error page instead of data. Only the real browser succeeded. Automation must drive an actual browser, not call this endpoint from a script.

### 2. Xplan — Planning Administration's GIS layer (ArcGIS)
- The Planning Administration itself describes Xplan (on data.gov.il, `iplan` organization) as a tool showing all plans in progress, with the ability to **search by number, name, unique event number, place** — exactly the key we need.
- URL: `https://ags.iplan.gov.il/xplan/` (map interface) and `https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer` (ArcGIS REST layer — a standard format supporting `query?where=...&f=json` queries).
- **Confirmed blocked for scripts (tested locally from Israel):** `Invoke-RestMethod` to `MapServer?f=json` returned the same gov.il WAF "page not found" error page — same bot-protection issue as Mavat, not geographic.
- Not usable via plain script; would need the same browser-automation approach as Mavat if pursued.

### 3. data.gov.il (open data portal) — API works, but not a fit for this purpose
- The API (CKAN, `data.gov.il/api/3/action/...`) **does work** and was tested successfully.
- There's a dedicated `iplan` organization with 13 datasets, but they're at the national/district plan level (national outline plans, district outline plans, national infrastructure, planning regions) — **not** a local plan registry at the individual-project level with live status. Not suitable as a source for diffing against `plan_current`.

### 4. Rishuy Zamin (רישוי זמין)
- This is a **building permit** platform (after a plan is already approved) — not a source for the plan's own status/stages. Less relevant to this task (tracking plan stages and new plans); possibly relevant later for the permit/construction stage.

## Recommendation
1. **Mavat** = confirmed, working, authoritative source for plan number → status/stages/dates/committee history (exactly as anticipated in `framework_spec.md`).
2. Build the daily pull as a **browser-automation task** (e.g. a Claude in Chrome scheduled task, one run per `plan_current`): search the plan number → land on the `SV4` detail page → extract current status/date and the committee-decision table → diff against `status_events.is_current` in `projects.db` → flag changes. **Confirmed (not just suspected): a plain server-side script cannot call the REST endpoint directly** — both domains sit behind WAF/bot-detection (F5-style challenge cookies) that require real browser JS execution, tested and reproduced from an Israeli IP.
3. **Xplan (ArcGIS)** — confirmed blocked for scripts too (same WAF). Not pursued further; Mavat alone covers what we need for status tracking.
4. data.gov.il and Rishuy Zamin — not relevant for the current purpose.

## Remaining open items (next session)
- Map Mavat's meeting-status vocabulary (e.g. "קבצים מצורפים", meeting types/statuses seen in the committee table) onto our 33-code `STAGE_LABEL` vocabulary in `build_db.py`.
- Confirm the plan-number → `mid` resolution step reliably (test a few more plan numbers, including old-format ones like `הל/מח/567`) — new-format numbers (`457-1253954`) worked; old-format behavior is untested.
- Design "new plan discovery" (plans not yet in the Vault) — Mavat's search-by-city/area filters (מרחב תכנון, ישוב/רשות מקומית) look usable for this; untested so far.
- Build the scheduled Claude in Chrome task (or Playwright-based automation) that does the search → extract → diff → alert cycle for each `plan_current`; direct script access to the REST endpoint is ruled out.

---

## Playwright automation — built & tested (session 2026-07-06)

Prototype lives in `mavat_scraper/` (Python venv at `mavat_scraper/venv`, Playwright +
Chromium installed). Main script: `mavat_scraper/mavat_status.py`. All results below are
from **real runs against the live site from the user's Israeli IP**, not theory.

### Verdict: headless Playwright works — this can be an unattended scheduled job
- **A real browser engine is still required** (plain HTTP is dead, as before). But
  **headless Chromium passes the WAF** — every test plan resolved headless. No
  `playwright-stealth` / `patchright` needed.
- The WAF does **not** fingerprint headless/webdriver: `navigator.webdriver` is `true`
  even in **headed** mode and the site serves data anyway. It only requires genuine
  in-browser JS execution. → No display / no logged-in desktop needed on the server.
- **Even an in-page `fetch()`** to `/rest/api/SV4/1?mid=...` from a warmed, WAF-passed
  page returns the 404 WAF page. The server distinguishes the SPA's own XHR from an
  injected fetch. **So we must drive the real search UI**, not call the API directly.

### Best extraction path: the search call, not the detail page
- Submitting a plan number in the "מספר תכנית" field triggers `POST /rest/api/sv3/Search`,
  whose result **row already contains the current status + status code + status date** —
  enough for the daily "did the status change, and when" check. **No SV4 detail page and
  no committee-history needed for the quick check.**
- Fields captured per plan: `UNIFIED_STATUS_DESC` (e.g. "אישור"),
  `INTERNET_SHORT_STATUS` ("פרסום אישור"), `INTERNET_STATUS_CODE` (stable numeric code,
  e.g. `4480` — ideal for diffing), `INTERNET_STATUS_DATE`, `BI_STATUS_DATE`, `MP_ID` (=mid).
- Verified: `457-1253954` → אישור, decision date `28/06/2026` (matches prior manual test).
- Committee-decision history is **not** in the search row; it needs the SV4 detail XHR
  (`/rest/api/SV4/1?mid=`), which fires only on a fresh SV4 page load (intercept the SPA's
  own call — the injected fetch is blocked). Deferred: not needed for the status check.

### Timings (headless, real)
- Cold (fresh browser context per plan): **~7.0s avg**.
- Warm (one reused context, many lookups): **~6.1s avg**. Warm saves little (~0.8s) only
  because each lookup currently reloads the full search SPA. A further optimization
  (re-search inside the already-loaded SPA without `goto`) is noted but not built.
- Projection: **~1,000 plans ≈ 100 min single-threaded; ~30-35 min at concurrency 3.**

### Gotchas found & handled
- Search defaults to a "תכניות שנדונו בטווח של 3 חודשים" (last-3-months) radio that hides
  older plans → script selects **"כל התכניות"** (all plans) first, else false misses.
- The plan-number `<input>`'s `id` contains a space; use the stable selector
  `input[aria-label='מספר תכנית']`, not an id selector.
- A miss originally burned the full ~39s timeout; fixed to fail fast (~6s) by waiting for
  the specific post-submit search response.

### robots.txt
- Permissive: only disallows `*.gif/*.jpg/*.jpeg/*.pdf`. Nothing blocks `/SV3`, `/SV4`, or
  `/rest/api/`. Script already blocks image/font requests and reuses one context; still
  need to add polite inter-request delays + keep concurrency low.

### Scope decisions (this session)
- **Old-format Hebrew plan numbers dropped** — none in scope need status updates.
  (`הל/מח/567` did resolve; `הצ/1-1/394א` did not — formatting/existence unclear.)
- Committee history not pursued (quick check only needs status + date).

### Still to do (next session)
- Run the **concurrency test** (`mavat_scraper/conc_test.py`, 3 parallel contexts) and
  watch for WAF/IP blocks before scaling.
- Add polite rate-limiting (inter-request delay) to `mavat_status.py`.
- Wire the search → extract → diff-against-`status_events` → alert cycle into the pipeline.

---

## Hardening + daily diff layer — built & tested (session 2026-07-08 C)

### Reliability fix (the big one)
The SV3 page fires its own **generic** `sv3/Search` calls (on page load and on the
"כל התכניות" filter click). The old wait loop treated *any* new search response as "our
query returned," so a late generic response ended the wait early → intermittent false
MISS sequentially, and near-total MISS under concurrency. Fixed in both scripts by
matching the response's **request payload** to the plan number (only OUR query ends the
wait). Details in `BUG_REFERENCE.md`.

### Concurrency verdict (clean re-run, post-fix)
- 3 parallel contexts × 5 plans: **fully consistent** OK/MISS across workers, **0 non-200
  responses** — no WAF pushback at concurrency 3.
- Effective throughput at 3×: **~5s per lookup** (warm sequential hit: 7–9s today).

### Hardening added to `mavat_status.py`
- `--delay` polite inter-request delay (default **2.0s**).
- Retry-once-on-miss with 5s backoff (`--no-retry` to disable) — misses were observed to
  be transient; a persistent miss after retry is a real "not found by number search".

### Daily diff layer: `mavat_scraper/mavat_diff.py`
- Loads all distinct **new-format** plan numbers from `projects.db` (3,025 as of today)
  with vault context (city/name/current vault stage).
- Looks each up (warm session, delay, retry, session recycled every 250 lookups) and
  compares to the previous snapshot in **`mavat_scraper/mavat_state.db`** — its own DB,
  because `projects.db` is rebuilt daily by `RefreshProjectsDB` and would wipe any added
  table. Results are committed **incrementally** (a killed long run keeps its progress).
- Change signal: `status_desc` OR `status_date` changed. `status_code` is ignored as a
  signal (observed changing while the label stayed put). Changes are appended to
  `mavat_changes` and reported (console + optional `--report out.md` Markdown table).
- Modes: `--plans a,b,c` (explicit) / `--rotate N` (N least-recently-checked — enables
  chunked coverage) / `--all` (full sweep).
- **Verified live**: first run snapshots, second run reports no change; misses recorded.

### Second reliability fix: verified 'כל התכניות' selection
A first sample batch showed ~90% false misses: the all-plans filter click was silently
failing under slow SPA renders, so searches ran with the default last-3-months filter and
hid plans without recent activity. Fixed by verifying the (custom ARIA) radio is actually
checked before searching; unverifiable filter → `error=filter_not_set` (plan left for the
next rotation, never recorded as a miss). Details in `BUG_REFERENCE.md`. After the fix, a
15-plan rotation run matched 12/15 (2 likely-genuine misses, 1 filter error re-queued).

### Dormant plans (approved = stop rescraping) — decided with user 2026-07-08
- `mavat_state.db.mavat_status.dormant` flag: set when Mavat returns **אישור**
  (`TERMINAL_MAVAT_STATUSES`); plans whose *vault* current stage is `approved`
  (`TERMINAL_VAULT_STAGES`) are likewise excluded from selection.
- `--rotate`/`--all` skip dormant/approved plans automatically; `--include-dormant`
  overrides. As of the first sample: **1,035 of 3,025 tracked plans skipped** → ~1,990
  active. Observation: most first-time snapshots came back אישור (vault lags Mavat), so
  the active pool shrinks further with every rotation pass.
- **נדחתה** (rejected) added to `TERMINAL_MAVAT_STATUSES` (user decision, 2026-07-08).

### Full-sweep projections (~1,990 active plans after dormant exclusion)
- Today's per-lookup: ~11–16s warm (site slower than the ~6s benchmark; the verified
  filter selection adds ~1–2s). Sequential + 2s delay: **~7–9h**; concurrency 3: **~3h**;
  `--rotate 300` nightly: **~1.2h/night**, full active coverage in ~1 week.
- **Decision 2026-07-08: no scheduled task yet** — manual runs first, cadence to be chosen
  after watching a few runs.

---

## New-plan discovery layer — built (session 2026-07-09)

**Goal (user spec)**: find NEW plans nationwide as they enter the pipeline, defined by six
early statuses: בבדיקה תכנונית, בבדיקת תנאי סף, תסקיר סביבתי, ניתנה הוראת המועצה הארצית,
דיונים ועריכת מסמך סביבתי, הכנת הודעה 77/78. All hits are surfaced; the user flags
exclusions (with reasons) in a review page, and the reasons drive iterative filter tuning.

### Mechanics discovered (probing session, all verified live)
- **תאריך הסטטוס האחרון** date field works — but it is a masked input: must be TYPED
  (`keyboard.type`), `fill()` is silently rejected. This is the primary sweep filter.
- **The סטטוס dropdown cannot be driven headless** (PrimeNG `p-autocomplete`; its option
  panel never populates). Status filtering is therefore done client-side on the harvested
  rows. (The sort dropdown, a different widget, DOES render `role=option` items.)
- **Paging**: page 1 returns 20 rows; each 'הצג עוד' click POSTs `_page`+1 and returns 50.
  The site stops serving 'הצג עוד' at ~**1,470 rows** per result list (hard display cap).
- **plNumber is a PREFIX filter** — `101-` returns the whole Jerusalem district. This
  enables recursive slicing past the display cap: any slice > ~1,400 rows splits into
  `P0`..`P9`. Covers all new-format numbers; old-format numbers are not sliceable (gap is
  logged after each backfill).
- **יצוא דו"ח (export) is dead in headless** — zero network activity on click.
- Responses are matched to requests by payload (`plNumber`, `dateLastStatusDate`) — the
  page fires its own generic searches on load/radio-toggle (same race as the status
  scraper; see BUG_REFERENCE).

### Files & flow
- `mavat_scraper/mavat_discover.py` — the sweep.
  - Routine: `mavat_discover.py` (defaults to last sweep date) — one nationwide search,
    fine under the cap for weekly windows (~190 status-changes/week nationwide).
  - Backfill: `mavat_discover.py --since DD/MM/YYYY --backfill` — recursive prefix slicing.
  - `--count-only`, `--max-pages`, `--export-json` utilities.
- `mavat_scraper/mavat_discovery.db` — `discovered` (one row per plan ever seen; flags:
  `target_status`, `in_vault`, `excluded`+reason+comment) and `sweeps` (run log).
- `make_review_page.py` → **`mavat_review.html`** — self-contained interactive review page
  (RTL; status chips; free-text search; per-plan להזנה/להחריג + reason presets + comment;
  decisions persist in localStorage; יצוא החלטות downloads a decisions JSON).
- `apply_review.py <decisions.json>` — writes decisions back to the DB and prints the
  exclusion-reason breakdown (the filter-tuning input).

### Review workflow (iterative, per user decision 2026-07-09)
1. Sweep → `make_review_page.py` → user reviews in browser → export decisions JSON.
2. `apply_review.py` ingests decisions (sets `excluded`/`kept`); decided plans never
   reappear. `kept=1` also shields a plan from automatic rules.
3. Recurring exclusion reasons become rules in **`auto_rules.py`**. "Kept" plans are
   entered into the vault by hand; the next DB rebuild + sweep flips them to `in_vault`
   and out of the candidate pool.

### Automatic exclusion rules (`auto_rules.py`) — round 1 (2026-07-12)
Derived from the user's first review pass. Only OPEN candidates are touched; every auto
exclusion is tagged `אוטומטי: <rule>` (auditable in the review page, `--revert` undoes all).
- Name patterns: שינוי קווי בניין; הסדרת מצב קיים/לגליזציה; איחוד וחלוקה/חלוקת מגרשים/
  פיצול מגרש; בריכות שחייה/חומרי גמר/מיקום חניות.
- Bedouin settlements (list in the script): everything except whole-neighborhood plans.
- **Positive-signal guard**: names with תוספת זכויות/יח"ד/קומות, הגדלת זכויות, שינוי ייעוד,
  פינוי-בינוי, התחדשות, מתחם, שכונ… are never auto-excluded.
- First application: 333 of 3,172 open candidates excluded → 2,842 open.

### Units tagging (`mavat_discover.py --tag-units 10`)
The search rows carry NO unit counts, but the form's "מספר יחידות דיור החל מ" filter does
(payload `residentialUnit` — numeric, not quoted). A tagging sweep re-harvests the window
with units>=10 set and flags matching plans (`units_ge10` column). 6,473 of 22,522 records
since 2022 clear the bar. Used for the "exclude <10 units" rule — with care: non-residential
plans and pre-quantity early-stage plans also lack the tag and must not be blanket-excluded.

### Status statuses — final target set (user decisions 2026-07-09 + 2026-07-12)
בבדיקה תכנונית, בבדיקת תנאי סף, תסקיר סביבתי, הכנת הודעה 77/78, Pre-Ruling.
(ניתנה הוראת המועצה הארצית and דיונים ועריכת מסמך סביבתי do not exist as Mavat
`UNIFIED_STATUS_DESC` values — 0 occurrences in 20,936 harvested rows.)

### Ignored transitions (user decision 2026-07-13)
**בהליך אישור** is never surfaced as a reportable change — the user does not track this
intermediate status manually in the vault. `IGNORED_NEW_STATUSES` in `mavat_diff.py`
(easy to extend). The snapshot in `mavat_status` is still updated silently to the true
current status, so a LATER real transition (e.g. → אישור) is correctly diffed against
the actual prior state, not artificially reset — it just never generates its own
approval-page row. Existing pending rows for this status were marked
`approved=0, note='auto-ignored...'` retroactively on 2026-07-13.

### Change-approval flow + units tracking (built 2026-07-13, user request)
- **SV4 details**: `MavatSession.fetch_detail(mid)` loads the plan's SV4 page and
  intercepts the SPA's own `/rest/api/SV4/1` XHR (direct calls stay WAF-blocked).
  `rsQuantities` rows carry authorised+added quantities; units = the 'מגורים (יח"ד)'
  row (code 120), total = AUTHORISED + ADD (verified: 457-1253954 → 114+250=364).
- **mavat_diff.py**: on every detected status change the plan's details are fetched and
  unit changes recorded alongside (`mavat_changes.old_units/new_units`). `--details N`
  additionally baselines N plans per run (nightly bat uses 25 → full baseline in ~2 months);
  a units change without a status change is logged as a `units-only` change row.
- **mavat_changes.html** (`make_changes_page.py`, regenerated each nightly run): approval
  page for pending changes — אשר/דחה + comment, export decisions JSON.
- **apply_changes.py <decisions.json>**: approved changes are APPENDED to the vault as
  `- סטטוס:: <label> <date>` in the block anchored by `תכנית:: <plan>`; an existing
  `(נוכחי)` marker moves to the new line; duplicate lines are refused; then
  `refresh_db.py` reruns so projects.db is current immediately. Rejected changes never
  reappear. This is the ONLY path that writes to the vault, and only on explicit
  user approval per change (sandbox-tested on a vault copy 2026-07-13).

### Mavat status labels observed so far (for the STAGE_LABEL mapping)
Counts from the first ~330 snapshots (2026-07-08):

| Mavat `UNIFIED_STATUS_DESC` | seen | suggested `stage_code` |
|---|---|---|
| אישור | 107 | approved |
| במילוי תנאים להפקדה | 78 | deposit_conditioned |
| נדחתה | 38 | plan_stopped |
| הכרעה בהתנגדויות / אישור | 35 | objections |
| בבדיקה תכנונית | 28 | planning_review |
| הפקדה להתנגדויות/השגות | 22 | deposited |
| בהליך אישור | 17 | approved_conditioned (tentative — verify meaning) |
| בבדיקת תנאי סף | 1 | thresholds |

Grow as rotation runs accumulate
(`SELECT DISTINCT status_desc FROM mavat_status` in `mavat_state.db`).

---

## Local-committee discovery integration (built 2026-07-13)

**Goal (user request)**: use `C:\R_PROJECTS\local_committee_scrapers` — a separate,
pre-existing project scraping 133 Israeli local planning committees (70 Complot + 63
Bartech) — as an additional, earlier-stage new-plan discovery channel, feeding the same
review workflow as the Mavat-side discovery above. Local committees see plans before
Mavat does (workflow: local-committee preapproval → Mavat submission → Mavat approval).

### Decision: don't fork the code, orchestrate + import from here
That project is a broader tool (own venv, own conventions, also covers committee
protocols/permits) with its own scheduled task. Forking just the plans-scraping piece
into `projects_monitor` means two copies to maintain and silent drift from fixes made
upstream. Instead: invoke its existing code for a daily subset of municipalities, then
import its output CSVs — no scraping logic duplicated.

### Root-cause fix: daily rotation instead of one weekly burst
Diagnosed 2026-07-13: the project's own weekly task ("Municipal Plans Weekly Update")
failed completely on 2026-06-24 — all 70 Complot municipalities hit
`ConnectionResetError 10054` (server actively closing the connection), the classic
signature of anti-scraping rate-limiting, not a permanent block (the host tested fully
healthy, HTTP 200, on 2026-07-13). Root cause: **all 70 Complot municipalities share one
physical backend**, `handasi.complot.co.il`, and the existing pacing (2s between
municipalities, no delay between individual plan-detail requests within one
municipality) is thin for a shared host serving 70 clients in one weekly blast.
**Fix**: spread the same total scraping across every day instead — `CommitteeSweep`
(daily, 10 least-recently-scraped municipalities → full 70-muni cycle in ~1 week) is
gentler on the shared backend by construction, not just a scheduling preference.
The old weekly task was **disabled** 2026-07-13 (superseded, not duplicated).

### Bartech is currently excluded (separate, unrelated breakage)
`local_committee_scrapers`' Bartech plans scraper uses Selenium +
`undetected-chromedriver`; Chrome auto-updated on this machine (v149) past what the
pinned ChromeDriver supports, breaking it independent of the rate-limiting issue above.
A promising lead, not yet pursued: `C:\R_PROJECTS\Project_update_scraper` (a newer,
separate project) scrapes Bartech *permits* via plain `requests` — its scraper found
the CAPTCHA isn't server-enforced (`g-recaptcha-response=x` dummy value works). A
Playwright network capture against Bartech's *plans* search (`SearchCityPlan`)
confirmed it fires real XHR/POST requests, suggesting the same gap may exist there —
which would mean rewriting Bartech-plans as pure HTTP rather than patching
ChromeDriver. Deferred; `CommitteeSweep` runs Complot only (`--systems complot`,
the default) until resolved.

### Files (`projects_monitor/committee_scraper/`, mirrors `mavat_scraper/`'s pattern)
- `run_committee_sweep.py` — `--count N` (rotation) or `--munis a b c` (explicit).
  Fetches `MUNI_REGISTRY` live from the scraper project's own venv (never duplicated/
  hardcoded, so it can't drift) to pick municipalities; invokes that project's venv +
  `run_subset.py` (see below) for the batch; imports each municipality's
  `<slug>-plans-master-table.csv` into `committee_state.db`.
- `committee_state.db` — `committee_muni_state` (per-muni last-scraped timestamp, for
  rotation) and `committee_candidates` (one row per muni::plan_number ever seen;
  excluded/kept/comment/decided_at mirror `mavat_discovery.db`'s shape).
- `run_committee_sweep.bat` — nightly wrapper (scheduled as `CommitteeSweep`).

### Additive change to the OTHER project (non-destructive)
`local_committee_scrapers\unified_scraper\municipal_scraper\run_subset.py` — new file,
added 2026-07-13, does not touch any existing script. Mirrors
`run_complot_fresh_scrape.py`'s CLI pattern but accepts a mixed Complot+Bartech
municipality list and uses the same 1-year rolling window as the daily/weekly job
(`run_daily_update.py`), writing to the same output CSVs so it composes with existing
baselines.

### Dedup with Mavat (user decision 2026-07-13)
The committee master CSVs carry a **קישור למבאת** (Mavat link) column — populated once
a plan has entered the Mavat pipeline. This is used directly as the "graduation" signal
instead of fragile plan-number matching across the two systems' different numbering
formats (committee plans are frequently old-format, e.g. `חל/1/ד- 41`, which cannot
string-match Mavat's `NNN-NNNNNNN` format). On import: a committee candidate whose
Mavat link is populated (at first sight or on a later re-scrape) is auto-"graduated" —
excluded from the review queue, link retained for reference, never surfaced as if it
still needed committee-level tracking. Secondary safety net: plan number cross-checked
against the vault (`projects.db.plan_current`, any format) for the same reason. The
Mavat link's URL often directly encodes the Mavat plan number
(`...SV3?text=304-0840322`) — parsed and stored (`mavat_plan_number` column) for future
cross-referencing.

**Verified live** (Haifa, 2026-07-13): 238 plans scraped, 124 auto-graduated
(already had a Mavat link or matched a vault plan number), 114 genuinely open new
committee candidates — merged into the unified review page on first run.

### Unified review page
`mavat_scraper/make_review_page.py` now merges both sources (`mavat_discovery.db` +
`committee_state.db`) into one `mavat_review.html`, tagged `source: 'mavat'|'committee'`
with a filter chip for each. Decisions are keyed by a per-source-unique id (bare plan
number for Mavat rows; `muni::plan_number` for committee rows — the `::` makes
collisions between the two structurally impossible). `apply_review.py` routes each
decision to the correct database by that id shape.
