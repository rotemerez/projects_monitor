# Session Handoff — 2026-07-22 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_21_A.md`. Short, focused session: reviewed a
decisions export for new auto-rule patterns, and closed out the repo-hygiene work from
yesterday by pushing to `origin/main`.

## What was built / fixed

1. **R6 — blocked regional-council municipalities** (`mavat_scraper/auto_rules.py`,
   committee-only): reviewed `docs/mavat_review_decisions (6).json` (11,905 decisions)
   looking for new exclusion patterns. Found that 18 regional councils (מועצות אזוריות —
   dispersed rural kibbutz/moshav committees) have a **0% keep rate across their entire
   history** — thousands of rejections each (lev hagalil 2,525, mateh yehuda 1,591,
   ma'ale hagalil 327, giv'ot alonim 342, ma'ale naftali 273, emeq hayarden 267, merom
   hagalil 253, biq'at beit hakerem 300, hagalil center 147, menashe alona 125, iron 119,
   misgav 88, kessem 79, lakhish 60, ma'ale hermon 59, hagilboa 55, harel 21, hagalil
   lower 19). Added `BLOCKED_COMMITTEE_MUNIS`, an **unconditional** auto-exclusion — no
   content override, unlike every other rule — because testing showed 331 already-
   excluded plans in these same councils already contained a nominal "positive signal"
   keyword (שכונ/תוספת יח"ד/מתחם) and were rejected anyway; in this context those words
   usually mean "add a 3rd unit to one farm plot" or "internal industrial zone," not real
   development.
   - **`mitar` (Meitar) was checked individually and excluded from the blocklist**: unlike
     the other 18, it covers real Bedouin towns (Hura) with a genuine open neighborhood
     candidate (`652-0754705`, "חורה - שכונה 27"). Caught specifically by cross-checking
     open candidates per municipality before applying anything — the user asked to review
     per-muni rather than approve the whole list at once, which is exactly what surfaced
     this exception.
   - Applied once: **1,464 committee candidates** auto-excluded.
2. **`ENERGY_RULE` regex broadened** (`(פוטו|אגרו).?וולט`, was `פוטו.?וולט` only): missed
   `אגרו וולטאי` (agro-voltaic — solar panels over active farmland), confirmed on
   `206-1183003` (manually rejected "not interested in photo voltaic fields" despite being
   an energy plan the rule should have caught). 10 more candidates (7 mavat + 3 committee)
   caught on the same run.
3. `mavat_review.html` regenerated: 14,511 open candidates (3,373 mavat, 11,138 committee),
   down from before by the ~1,474 excluded above.
4. Docs updated to reflect the above: `CLAUDE.md` (session history), `next_steps.md`,
   `docs/VERSION_LOG.md`, `docs/BUG_REFERENCE.md`.
5. **Pushed to `origin/main`**: this commit plus yesterday's previously-uncommitted
   backlog (see `SESSION_HANDOFF_2026_07_21_A.md`) — the repo had been 1 commit ahead of
   `origin/main` since 2026-07-13 with nothing pushed.

## Decisions made (should not be re-litigated)

- **R6 has no content-based override, by design.** Don't "fix" this later by adding a
  שכונ/תוספת יח"ד/מתחם carve-out to R6 without re-checking against the 331-plan
  counterexample above — that override was tested and rejected for this specific rule.
- **`mitar` stays off the blocklist.** If it starts showing a long run of rejections with
  no keeps (mirroring the other 18), it may be worth reconsidering, but as of this session
  it has a live counterexample.

## Current state / open loops

- `docs/mavat_review_decisions (6).json` and the two rural-planning spreadsheet files
  (`docs/rural-planning_index1.xls`, `docs/קובץ יישובים.xlsx`) remain untracked/uncommitted
  on disk — user hasn't yet said whether to delete the decisions JSON now that it's been
  applied (prior rounds' equivalents were left in place in Downloads, not deleted).
- Same open loops as prior handoffs otherwise (60 kept plans awaiting manual vault entry,
  etc.) — nothing this session touched those.

## Files touched this session

- `mavat_scraper/auto_rules.py` — `BLOCKED_COMMITTEE_MUNIS` (R6), broadened `ENERGY_RULE`.
- `CLAUDE.md`, `next_steps.md`, `docs/VERSION_LOG.md`, `docs/BUG_REFERENCE.md` — documented
  the above.
- `mavat_scraper/mavat_review.html` — regenerated (not committed; generated output).
- `mavat_discovery.db` / `committee_state.db` — 1,474 rows auto-excluded (generated state,
  not committed).
