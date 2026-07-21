# Session Handoff — 2026-07-21 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_19_A.md` (reconstructed retroactively same day as
this one, see that file). Two things happened today: real pipeline fixes (morning, per file
timestamps), and a repo-hygiene pass (this conversation) that found the whole project had
been running five sessions deep with **zero commits since 2026-07-13** and no handoff/
next_steps/CLAUDE.md updates past 2026-07-16.

## What was built / fixed (morning session, `auto_rules.py` / `make_review_page.py`)

1. **R3 (units<10 exclusion) now requires a CONFIRMED real unit count, never a placeholder**
   (`auto_rules.py:classify()`). Root cause: `416-1448794` (real units=15) got auto-excluded
   on its very first day, before `mavat_discover_units.py` ever got a chance to fetch its
   real count — every newly discovered row starts at `units_ge10=0` by default, which was
   being treated as equivalent to a real confirmed low count. Fixed by requiring
   `confirmed=True` (only set once a real fetch has happened) before R3 can fire at all; an
   unconfirmed low flag now does nothing — the plan just stays open until confirmed one way
   or the other instead of being silently pre-excluded on a guess.
2. **`בית פרטי (צמוד קרקע)` name-rule broadened** (`auto_rules.py:NAME_RULES`): originally
   required "צמוד קרקע" + a family-type qualifier (דו/חד משפחתי) together; a second case
   (`422-0907329`, אלעד) showed "צמוד קרקע" alone, with no qualifier, is already a strong
   enough single-dwelling signal. A genuine multi-unit/neighborhood plan still stays open
   regardless via the existing `POSITIVE_SIGNAL` override (`תוספת יח"ד`/`שכונ`/`מתחם`).
3. **Stale browser-cache bug fixed** (`make_review_page.py`, client-side JS): an
   auto-excluded plan that gets un-excluded server-side (rule fix, or reopened from the
   backlog) was staying "excluded" forever in a browser that had already loaded the page —
   `mavat_review_decisions_v1` in `localStorage` only ever seeded a plan's decision once.
   Root-caused via `502-1406529` (auto-excluded, then un-excluded by a same-day rule fix +
   backlog reopen, but stayed excluded in an already-open browser tab indefinitely). Fix:
   only decisions tagged `אוטומטי:` (auto-rule origin) are now re-synced from the DB on every
   page load to match current server state; any genuine human decision (any other reason,
   or `kept`/`rejected`/`approved` state) is left untouched.

## Repo-hygiene pass (this conversation, afternoon)

- Discovered the repo has only one commit (`d1305e7`, 2026-07-13) despite five sessions of
  real work since (07-14, 07-15/16, 07-19, and this one). `next_steps.md`/`CLAUDE.md`
  history sections had drifted to only cover through 07-16.
- Wrote `SESSION_HANDOFF_2026_07_19_A.md` retroactively to fill the undocumented gap for
  that session (best-effort reconstruction from file diffs, not a live log).
- Removed the stray `mavat_scraper/..mavat_report.md` (malformed filename, looked like an
  accidental output from a manual run on 2026-07-19, not a real deliverable).
- Updated `next_steps.md`, `CLAUDE.md`, `docs/BUG_REFERENCE.md`, `docs/VERSION_LOG.md` to
  cover the 07-19 and 07-21 work above.
- Committed everything accumulated since 2026-07-13, **excluding**
  `docs/rural-planning_index1.xls` and `docs/קובץ יישובים.xlsx` (per the 2026-07-16 decision:
  the rural-settlement classifier approach they were meant for was superseded by the
  description-text signal in `mavat_discover_units.py` and never carried further — left
  untracked/uncommitted, not deleted, in case that approach gets revisited).

## Decisions made (should not be re-litigated)

- **Commit hygiene going forward**: work should be committed at the end of each session (or
  more often) rather than accumulating silently — this gap was only caught because the user
  asked for a git-status comparison, not because anything broke.

## Current state / open loops

- Same open loops as `SESSION_HANDOFF_2026_07_16_A.md` (60 kept plans still awaiting manual
  vault entry, etc.) — nothing here resolved those.
- The two `.xls`/`.xlsx` rural-planning files remain untracked on disk; revisit only if that
  classifier approach comes back into scope.
