# Bug Reference

**Last Updated:** 2026-07-08

Known issues, root causes, and solutions. Newest on top.

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
