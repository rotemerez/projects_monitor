# Session Handoff — 2026-07-14 A

**Project root:** `C:\R_PROJECTS\projects_monitor`
Continues from `SESSION_HANDOFF_2026_07_13_A.md`. Full detail in `docs/MAVAT_AUTOMATION.md`
and `CLAUDE.md` (session history + scheduled-tasks section).

## What was built / fixed

1. **Bartech plans fixed** (was broken, excluded from `CommitteeSweep`): rewrote
   `local_committee_scrapers\unified_scraper\municipal_scraper\systems\bartech\plans.py`
   from Selenium to Playwright. Investigated an HTTP-rewrite lead first (Bartech
   *permits* work via plain `requests`, no CAPTCHA enforced) — **dead end for plans**: a
   live network capture + direct test confirmed Bartech's plans search enforces a real
   invisible reCAPTCHA v2 server-side (dummy token rejected). What actually worked: plain
   headless Playwright passes that same challenge on its own — the real bug was never
   "Bartech blocks bots," it was Selenium's ChromeDriver needing separate version-pinning
   against an auto-updating system Chrome, which Playwright's bundled Chromium sidesteps
   entirely. Verified live against Holon (497 plans, full detail-page enrichment).
   `committee_scraper/run_committee_sweep.py` now defaults to `--systems complot,bartech`.
   First live scheduled run (2026-07-14 08:00) succeeded: 6 Bartech + 4 Complot
   municipalities, 10/10 OK.

2. **`MavatDiscovery` scheduled task moved to daily 07:30** (was weekly Sunday), per user
   request.

3. **Mavat-graduation dedup gap found and fixed**: `run_committee_sweep.py`'s dedup
   logic only checked the committee scraper's own קישור למבאת column + the vault — it
   never cross-checked `mavat_discovery.db`'s own plan list. Found via a concrete
   duplicate (Ashdod plan `603-1218759`, already in `mavat_discovery.db` since 2026-07-09,
   but sitting open as a committee candidate because Complot's detail page never
   populated a Mavat link for it). A full check found 35 of 240 open committee
   candidates (~15%) in this state. Fix: `reconcile_with_mavat_discovery()`, runs every
   sweep against *all* open candidates (not just newly-scraped ones, since the two
   discovery sources run on independent schedules). Backfilled the 35 by hand.

4. **`auto_rules.py` extended to committee candidates** — previously touched only
   `mavat_discovery.db`; committee candidates never got any automatic exclusion. Added:
   - **R4** (committee-only): plan number not in standard local format (`NNN-NNNNNNN`) →
     excluded as national/old-format, tracked via Mavat instead. Matched **165 of 205**
     open committee candidates (83%) — found by reviewing a batch of manual decisions
     where the user was hand-rejecting this same shape repeatedly.
   - **R5** (both sources): obvious test/placeholder rows.
   - Wired `--committee-only` into `run_committee_sweep.bat` too (same-day cleanup,
     rather than waiting for the next `MavatDiscovery` run).
   - Result: open committee queue went from 205 → 0 in one pass.

5. **Export-button Hebrew corruption root-caused and fixed**: every decisions JSON
   exported from `mavat_review.html`/`mavat_changes.html` arrived with Hebrew mangled
   into `×`-led mojibake when pasted back into chat. Root cause: the download `Blob` had
   no UTF-8 BOM and no explicit charset (`type: 'application/json'`) — Hebrew's UTF-8
   lead byte (`0xD7`) reads as `×` under Windows-1252/cp1252. Fixed both export buttons
   (BOM prefix + `charset=utf-8`); `apply_review.py`/`apply_changes.py` now read with
   `utf-8-sig`. Verified end-to-end with a Playwright test that clicks export and
   inspects the downloaded bytes (BOM present, Hebrew decodes cleanly, `apply_review.py`
   parses without error).

6. **Review/changes queues cleared**: applied 15 pending Mavat status-change decisions
   (7 approved → written to vault + `projects.db` refreshed, 7 rejected, 1 already
   applied) and a batch of 22 kept-plan decisions (3 entered into the vault by hand:
   `תמל/1131`, `תמל/2073`, `152-1085646`, confirmed via `refresh_db.py` rerun).

7. **One-off vault content fix**: AZUR שלב א' קפלן 3 ו-5 (`אזור\אזור, יצחק שדה.md`) had a
   pasted Maya/TASE report URL with embedded line breaks, parsed into 6 bogus `- צפי::`
   bullets, polluting `exec_forecast`. Merged back to one line, URL dropped per user's
   call. Not a systemic parser bug — didn't search for other instances since the
   corruption is specific to how that one URL got pasted.

8. **Housekeeping decisions (not tasks)**: keep the `·משוער` marker on derived vault
   fields; `project_type` classification is **not worth further investment** — nothing in
   the codebase reads it, it was never actually requested. Deleted obsolete one-off logs
   in `mavat_scraper\`.

## Current state / open loops

- **Mavat review queue**: ~1,400+ open Mavat-source candidates still being worked
  through (post-backfill backlog, unaffected by today's committee-side fixes). Committee
  queue: 0 open (freshly cleared — will refill daily as `CommitteeSweep`/`MavatDiscovery`
  run, now largely pre-filtered by R4/R5).
- **Kept-plans queue**: 19 Mavat-source plans still deliberately untracked from the last
  batch (user's call, not an oversight) + 0 committee-source kept-not-yet-entered.
- **Pending Mavat status changes**: 0.
- **Scheduled tasks now**: `RefreshProjectsDB` 06:00, `MavatDiscovery` 07:30 (daily),
  `MavatStatusDiff` 07:00, `CommitteeSweep` 08:00 (`complot,bartech`, includes
  `auto_rules.py --committee-only` now).
- Nothing currently broken or blocked. Bartech, dedup, and scheduling items from
  `SESSION_HANDOFF_2026_07_13_A.md`'s open-loops are all resolved.

## Files touched this session (for quick orientation)
- `local_committee_scrapers\...\systems\bartech\plans.py` — Selenium → Playwright rewrite
  (other project, additive).
- `committee_scraper/run_committee_sweep.py` — `--systems` default, `reconcile_with_
  mavat_discovery()`, `mavat_discovery_plans()`.
- `committee_scraper/run_committee_sweep.bat` — added `auto_rules.py --committee-only`.
- `mavat_scraper/auto_rules.py` — rewritten: `apply_to_mavat()` / `apply_to_committee()`
  split, R4/R5, `--mavat-only`/`--committee-only`/`--revert` (both sources).
- `mavat_scraper/make_review_page.py`, `make_changes_page.py` — export button BOM/charset
  fix.
- `mavat_scraper/apply_review.py`, `apply_changes.py` — `utf-8-sig` read.
- Vault: `אזור\אזור, יצחק שדה.md` (URL-corruption fix), plus vault entries for 3 kept
  plans and 7 approved status changes (user/automation, not listed individually here).
- Scheduled tasks: `MavatDiscovery` trigger changed to daily.
