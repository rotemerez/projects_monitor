# Bug Reference

**Last Updated:** 2026-07-21

Known issues, root causes, and solutions. Newest on top.

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
