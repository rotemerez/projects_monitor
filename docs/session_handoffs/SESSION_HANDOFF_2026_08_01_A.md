# Session Handoff — 2026-08-01 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_22_A.md`. Spans several days of the same ongoing
thread (2026-07-26 through 2026-08-01): the user pasted a stream of Complot
backend-link/frontend-link pairs, one municipality at a time, to fix broken review-page
links — which surfaced two real underlying data bugs in the shared Complot `site_id`
registry along the way.

## What was built / fixed

1. **21 new Complot frontend-link overrides** added to `COMPLOT_MUNI_LINK_OVERRIDES`
   (`committee_scraper/run_committee_sweep.py`), each confirmed against a real
   user-supplied backend/frontend link pair and backfilled into existing
   `committee_state.db` rows, then `mavat_review.html` regenerated after each:
   Migdal Ha'emeq, Modi'in, Mordot Carmel, Nahariya, Ofaqim, Or Yehuda, Petah Tikva,
   Qiryat Gat, Qiryat Malakhi, Raanana, Rahat, Ramat Gan, Ramat Hasharon, Rehovot,
   Rishon LeZion, Saronim, Sderot, Sdot Dan, Tiberias, Yavne, Yeruham.
   - Most reused an already-known template (`iron`'s `/binyan/#taba/<id>`, or
     `kfar saba`'s `/newengine/Pages/taba2.aspx#taba/<id>`).
   - Six needed a brand-new lambda for a previously-unseen page path: Migdal Ha'emeq
     (`_MIGDAL_HAEMEQ_LINK`), Nahariya (`_NAHARIYA_LINK`), Petah Tikva
     (`_PETAH_TIKVA_LINK`), Raanana (`_RAANANA_LINK`), Rishon LeZion
     (`_RISHON_LEZION_LINK`, a hardcoded-domain override like `givatayim` — its real
     frontend is on `www.rishonlezion.muni.il`, not the registry's own
     `rishonlezion.complot.co.il`), and Yavne (`_YAVNE_LINK`, `/taba2/` — a different
     path from the `/newengine/Pages/taba2.aspx` family despite similar naming).
   - Full reasoning/comments for every template are inline in `run_committee_sweep.py`
     directly above `COMPLOT_MUNI_LINK_OVERRIDES`.

2. **Tira/Hagalil Center `site_id` collision** — found from a user report ("many
   showing tira but being in the north"). `local_committee_scrapers`'s own
   `registry/dispatcher.py` had both `"tira"` and `"hagalil center"` registered with the
   identical Complot `site_id: 20`; confirmed all 240 `committee_state.db` rows tagged
   `muni='tira'` were exact plan-number duplicates of the already-correct
   `hagalil center` rows — Tira had never actually been scraped. User found Tira's real
   site_id (24) by reading a live search URL off Tira's own site. Fixed: corrected
   `dispatcher.py`, deleted the 240 duplicate rows, reset `tira`'s `last_scraped_at` so
   it re-scrapes fresh with the corrected id next rotation turn.

3. **Tzefat/Emek HaYarden mislabeling** — same root-cause family, found on a closer
   look at plan `214-0907980` (initially, wrongly, assessed as "not a bug" — see
   Decisions section below). All 79 rows tagged `muni='tzefat'` turned out to be
   genuine Jordan Valley (Emek HaYarden) content — one plan literally titled "תכנית
   אסטרטגית למרחב תכנון עמק הירדן." Tzefat's registered site_id (12) actually belongs to
   Emek HaYarden (confirmed independently: `emekhayarden.complot.co.il`'s own
   plan-search widget declares `site_id=12` itself). User found Tzefat's real site_id
   (88). Fixed: corrected `dispatcher.py`, retagged 76 of the 79 `tzefat` rows to
   `emeq hayarden` (3 were already exact duplicates there and got dropped), reset
   `tzefat`'s `last_scraped_at`.

4. **Systemic verification sweep**: rather than keep finding site_id bugs one at a
   time by accident, wrote a one-off probe script (plain HTTP, no browser/JS execution
   needed) across all 69 Complot-system registry entries. The real site_id is a static
   `<script>var site_id = N;</script>` string embedded in each municipality's own
   plan-search page. **Key gotcha discovered along the way**: several municipalities'
   `/binyan/` pages are uncustomized, copy-pasted WordPress/Elementor demo content that
   verbatim shows a *different, unrelated real client's* site_id (several showed Emek
   HaYarden's own value, one showed Taibeh's, one showed Bat Yam's) — a real trap for
   any naive "trust the first site_id string you find" automation; it would have
   produced 5 wrong "fixes" if not manually cross-checked. After the user verified each
   flagged case against a real search URL on each site (`GetTabaByNumber` /
   `GetTabaByAuthority` / `GetBakashotByInterestedParty`), only Tira and Tzefat's
   registry entries were actually wrong. Ten other candidates that looked suspicious or
   unresolved turned out to already be correct: `hagalil lower`, `ganei tikva`, `yavne`,
   `nazareth`, `menashe alona`, `nahariya`, `yoqne'am illit`, `bnei brak`, `givatayim`,
   `ariel`.

5. **One-off data query answered** (not a code change): found 111 vault-tracked plans
   (`projects.db`) where the Government/National Authority for Urban Renewal (הרשות
   הממשלתית/הארצית להתחדשות עירונית) is (co-)developer — deliberately excluding
   `החברה להתחדשות עירונית`, a different quasi-governmental *company* entity the user
   didn't ask for. Broke down how many are actually confirmed live on Mavat (37) vs.
   local/pre-filing-only (25: 20 on the תמ"ל track with no standard plan number yet, 5
   with no plan number at all) vs. formatted like a real Mavat number but not yet
   confirmed by the scraper's rotation (49, since only ~300 of ~2,000 active plans get
   checked per night).

## Decisions made (should not be re-litigated)

- **`_RISHON_LEZION_LINK` and `_GIVATAYIM_LINK` intentionally ignore the `base`
  (registry `muni_url`) parameter** and hardcode a different real domain — this is by
  design, not a bug to "simplify" later. Their registry `url` field is stale/wrong for
  frontend-linking purposes even though (per the systemic sweep) `givatayim`'s
  `site_id` itself is correct.
- **The Tira/Tzefat class of bug (two different municipalities sharing one Complot
  `site_id`) is a real, recurring failure mode in `local_committee_scrapers`'s own
  registry** — not something introduced by this project. If a similar "X is showing
  content from a completely different place" report comes in again, check for a
  `site_id` collision first (grep `dispatcher.py` for the suspect number), the same way
  these two were found.
- **Don't trust `/binyan/` (or any single candidate page) blindly as evidence of a
  municipality's real site_id.** Several of these pages serve copy-pasted demo content
  from an unrelated real client. Always cross-check via a second signal (a real user-
  confirmed search URL, or at minimum a distinct CSS client-code / GA-id that isn't
  shared with another municipality) before treating a discovered site_id as ground
  truth. The `probe_siteids.py` script (in the session's scratchpad, not checked into
  this repo) has the refined logic for this if the sweep needs re-running later.
- **Initial "not a bug" call on plan `214-0907980` was wrong** — don't repeat the
  mistake of trusting a single confirmed `siteid=` match as proof of correct labeling
  without checking the *content* of what that site_id actually serves.

## Current state / open loops

- **Tira has not yet been rescraped** with its corrected site_id (24) — its
  `committee_state.db` rows were deleted (the old wrong ones) but not yet replaced,
  since that requires `CommitteeSweep`'s daily rotation to pick Tira up again (its
  `last_scraped_at` was reset to force this). Once it has real data, get a real plan
  link pair from the user and add its frontend-link override (`/newengine/Pages/
  taba2.aspx`, per its homepage nav link, is the likely template — but per this
  project's own rule, needs a confirmed working example first, not just the page path).
- Same for **Tzefat** — real data not yet scraped under the corrected site_id (88);
  no frontend-link override added yet either.
- `docs/mavat_review_decisions (6).json`, a newer `(7).json`, and the two rural-planning
  spreadsheet files remain untracked/uncommitted on disk (same as prior handoffs) —
  user still hasn't said whether to delete these now that they've been applied.
- Same other open loops as prior handoffs otherwise (60 kept plans from 07-16 awaiting
  manual vault entry, etc.) — nothing this session touched those.
- Not all Complot municipalities have a confirmed frontend-link override yet — the
  user has been sending these one at a time as they notice broken links in
  `mavat_review.html`; expect more of these requests in future sessions.

## Files touched this session

- `committee_scraper/run_committee_sweep.py` — 21 new `COMPLOT_MUNI_LINK_OVERRIDES`
  entries (6 new lambdas), plus the `iron`-pattern batch list extended.
- `committee_scraper/committee_state.db` — backfilled `plan_link` for the 21
  municipalities above (generated state, not committed); deleted 240 mislabeled `tira`
  rows; retagged 76 mislabeled `tzefat` rows to `emeq hayarden`; reset `tira`/`tzefat`
  scrape timestamps.
- `mavat_scraper/mavat_review.html` — regenerated repeatedly (not committed, generated
  output); final count this session: 21,701 open candidates.
- `C:\R_PROJECTS\local_committee_scrapers\unified_scraper\municipal_scraper\registry\
  dispatcher.py` (a **different project**, outside this repo) — corrected `tira`'s
  site_id (20 -> 24) and `tzefat`'s site_id (12 -> 88).
- `CLAUDE.md`, `next_steps.md`, `docs/VERSION_LOG.md`, `docs/BUG_REFERENCE.md` —
  documented all of the above.
