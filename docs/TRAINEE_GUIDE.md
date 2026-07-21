# Trainee Guide — Projects Monitor

**Last updated:** 2026-07-19. This is the "how the whole thing actually works" explainer.
For deep-dive detail on any one piece, see the other docs linked at the end — this guide's
job is to give you the map before you go read the territory.

---

## 1. What this project is, in one paragraph

We track construction/urban-renewal projects (תכניות) across Israeli neighborhoods. A human
maintains an **Obsidian vault** (Markdown notes, one file per neighborhood) as the source of
truth. A daily pipeline turns that vault into a SQLite **database** (`projects.db`) for
analysis. On top of that, a family of scrapers watches מנהל התכנון (Mavat, the national
planning portal) and local planning-committee websites to (a) keep each tracked plan's status
current and (b) discover brand-new plans you don't know about yet. Everything that needs a
human judgment call — "is this plan worth tracking?", "did this status change really happen?"
— lands in one page, `mavat_review.html`, that you review and export decisions from.

## 2. The vault (source of truth)

- Lives in Dropbox: `מדלן תוכן\תכניות תחבורה\לוז פרויקטים\לוז פרויקטים\שכונות`.
- One Markdown file per neighborhood; one `#### <project name>` block per project inside it.
- Fields are Dataview-style inline: `- שדה:: ערך` (e.g. `- תכנית:: 457-1253954`,
  `- סטטוס:: הפקדה להתנגדויות/השגות 16/07/2026`).
- **Never edited by automation except one path**: an approved Mavat status-change writes a
  new `- סטטוס::` line into the matching block (see §6). Everything else in the vault is
  purely human-maintained.
- Full field-by-field spec: `docs/framework_spec.md`.

## 3. `projects.db` — the analysis layer

- Built fresh every morning from the vault by `scripts/refresh_db.py` (imports
  `scripts/build_db.py` for the parsing/vocabulary logic). Scheduled task
  **`RefreshProjectsDB`**, daily 06:00.
- Five tables: `projects` (~10,500 rows), `status_events`, `tenders`, `signatures`,
  `value_history`. Full schema: `docs/SCHEMAS.md`.
- **Join key for everything downstream**: `projects.plan_current` — the plan number Mavat
  also uses (new format `NNN-NNNNNNN`, e.g. `457-1253954`; old formats like `הל/מח/567` exist
  but are out of scope for Mavat automation).
- **Rebuild is atomic**: `refresh_db.py` writes to `projects.db.tmp` and atomically swaps it
  into place (`os.replace`) — fixed 2026-07-19 after a scheduled-task pile-up (machine woke
  from sleep late) let a concurrent reader see a mid-rebuild, momentarily-empty DB and skip an
  entire day's status diff silently. If you ever see a script report "0 tracked plans" or
  similar, suspect this class of bug first.

## 4. Three independent watchers

These are separate pipelines with separate jobs — don't conflate them.

### 4a. `MavatStatusDiff` — "did a plan I already track change status?"

- Script: `mavat_scraper/mavat_diff.py`. Scheduled daily 07:00 via `run_status_diff.bat`.
- Reads `plan_current` for every vault project (`load_tracked_plans()`), looks each one up on
  Mavat (headless Playwright — plain HTTP is WAF-blocked), and diffs the returned status
  against the last snapshot stored in `mavat_state.db` (table `mavat_status`).
- **Rotation, not full sweep**: `--rotate 300` checks the 300 *least-recently-checked* active
  plans per run (a full cycle over ~10,500 plans takes many days). Plans in a Mavat-terminal
  status (`dormant` flag) or already `אישור` in the vault stop rotating.
- A detected change only becomes something you're asked to approve if it clears the status
  whitelist — see §5's "9-status whitelist" note. Otherwise it updates the snapshot silently
  and moves on.
- `--details N` also detail-fetches N plans/run to backfill real unit counts, and (2026-07-19)
  distinguishes a **first-time deposit** from a **106(ב) re-deposit after corrections** by
  reading the plan's own stage-history log (`rsInternet` in the SV4 detail JSON) — Mavat's own
  top-line status bucket collapses both into the same generic `הפקדה להתנגדויות/השגות` label.

### 4b. `MavatDiscovery` — "is there a brand-new plan on Mavat I don't know about?"

- Scripts: `mavat_discover.py` (nationwide sweep) → `auto_rules.py` (auto-exclude known junk
  patterns) → `mavat_discover_units.py` (real unit counts + description-text signals for
  candidates in early submission stages) → `make_review_page.py` (regenerate the review page).
  Wired in that order in `run_discovery.bat`, daily 07:30.
- Only surfaces plans whose status is in the same **9-status whitelist** (see §5) —
  everything else is invisible to this pipeline entirely, by design.
- Candidates are matched against your vault (`in_vault` flag) — if already tracked, this
  becomes a **vault-notice** instead of a new-candidate row (see §5).

### 4c. `CommitteeSweep` — "is there a new plan at the local-committee stage, before it even
reaches Mavat?"

- Script: `committee_scraper/run_committee_sweep.py`, invoking a separate project
  (`local_committee_scrapers`) for **Complot** and **Bartech** municipality websites, daily
  08:00 via `run_committee_sweep.bat`.
- **Rotation**: 10 least-recently-scraped municipalities per day across ~133 total (roughly a
  2-week cycle) — deliberately spread out after a 2026-06-24 outage where a full-133 weekly
  burst rate-limited the shared Complot backend.
- **Dedup/graduation**: a committee candidate whose plan number is already in the vault, or
  already found by the independent Mavat nationwide sweep, is "graduated" (auto-excluded,
  reason recorded) rather than surfaced — the workflow is local-committee → Mavat → approval,
  and once a plan reaches Mavat there's no need to track it at the committee level too.
  **Do NOT trust the committee CSV's own `קישור למבאת` (Mavat link) column for this** — found
  2026-07-19 that both scrapers populate it as a templated search URL
  (`SV3?text=<plan_number>`) regardless of whether the plan actually exists on Mavat; live
  spot-checks came back "not found" for the large majority of link-only "graduated" rows. Only
  the two genuine cross-checks (vault match, Mavat-sweep match) are trusted now.
- No status filter on this side (unlike Mavat's whitelist) — every non-graduated, non-excluded
  committee candidate is fair game for the review page.

## 5. `mavat_review.html` — the one page you actually work in

Generated by `make_review_page.py`, regenerated at the end of every sweep above. It merges
**three row kinds** into one list (each with its own id shape so they can never collide):

| Kind | id shape | What it means | Your action |
|---|---|---|---|
| **candidate** | bare plan number (Mavat) or `muni::plan` (committee) | A new plan not yet in your vault | keep (enter into vault by hand) / exclude (with a reason) |
| **vault-notice** | bare plan number | A plan *already in your vault* just showed up in a Mavat sweep for the first time — worth a look since Mavat's page is often richer than the source it was entered from | one-click "seen" dismiss (never repeats) |
| **status-change** | `chg::<id>` | A vault-tracked plan reached a tracked status, or its unit count changed | approve (writes to the vault + refreshes `projects.db`) / reject |

**The 9-status whitelist** governs candidates, vault-notices, *and* status-changes alike (kept
in sync across `mavat_discover.py:TARGET_STATUSES`, `mavat_diff.py:MAVAT_TRACKED_STATUSES`,
`make_review_page.py:MAVAT_TRACKED_STATUSES`):
`הכנת הודעה 77/78`, `הכנת תכנית`, `Pre-Ruling`, `תסקיר סביבתי`, `בבדיקת תנאי סף`,
`בבדיקה תכנונית`, `הפקדה להתנגדויות/השגות`, `אישור`, `נדחתה`. Anything else is invisible on
purpose — it never becomes a row you have to deal with. Committee-side statuses (`בתכנון`,
`בהפקדה`) are always tracked with no such filter.

Decisions are kept in the browser's `localStorage` as you work, then **exported as JSON**
(`mavat_review_decisions (N).json` in Downloads) and fed back with `apply_review.py`.

## 6. `apply_review.py` — decisions flow back

```
venv\Scripts\python.exe apply_review.py "%USERPROFILE%\Downloads\mavat_review_decisions.json"
```

Routes each decision by id shape — never ambiguous:
- bare plan number → `mavat_discovery.db` (`discovered` table): sets excluded/kept/reason.
- `muni::plan` → `committee_scraper/committee_state.db`: same, for committee candidates.
- `chg::<id>` → `mavat_state.db` (`mavat_changes`): **approve** writes a new `- סטטוס::` line
  into the matching vault block (using the 106(ב)-aware label when applicable, see §4a) and
  reruns `refresh_db.py` automatically; **reject** just dismisses.

Also prints exclusion-reason stats (tuning input for `auto_rules.py`) and the current
kept-plans queue (plans awaiting manual vault entry).

## 7. `auto_rules.py` — the rule engine that keeps the queue small

Without this, every discovered candidate would need a human decision every single day. Instead,
content-based rules — mined from your own past decisions — auto-exclude known-uninteresting
shapes *before* they ever reach the review page, tagged `אוטומטי: ...` so they're always
auditable/revertible. Runs automatically as the last content step of both `MavatDiscovery` and
`CommitteeSweep`. Current rules (see the file's own docstring for the full history):

- **R1** — technical/no-development plans by name pattern: building-line changes, existing-
  situation regularization, lot consolidation/division without rights change, minor approved-
  plan tweaks (pools, parking, finishes), single religious-building plans. Since 2026-07-19,
  also scans the plan's Mavat description text (not just its name), since some plans carry only
  a developer/company name with the real content only visible in the description.
- **R2** — Bedouin settlements: excluded unless it's a whole-neighborhood plan (name contains
  `שכונ`).
- **R3** — fewer than 10 units and no other interesting component (commerce/industry/roads/
  public buildings/etc.), for submission-stage statuses where unit counts are meaningful.
- **R4** (committee-only) — plan number isn't the standard local-plan shape `NNN-NNNNNNN`
  (i.e. it's a national/old-format plan) → tracked via the Mavat sweep instead.
- **R5** — obvious scraper test/placeholder rows.
- A `POSITIVE_SIGNAL` override always wins: any of the R1 patterns is ignored if the name also
  signals real added development (rights/unit/floor additions, pinuy-binuy, "מתחם", "שכונ").

**Explicitly NOT a rule** (reverted after a false pattern-match in 2026-07-14/16): plans at
`הכנת הודעה 77/78` status are never auto-excluded — that stage is an early planning-intent
signal the user wants to keep seeing.

## 8. Scheduled tasks — what runs when

| Task | Time | Does |
|---|---|---|
| `RefreshProjectsDB` | 06:00 | vault → `projects.db` (atomic rebuild) |
| `MavatStatusDiff` | 07:00 | status diff for vault-tracked plans → `mavat_report.md` + review page |
| `MavatDiscovery` | 07:30 | nationwide new-plan sweep → auto-rules → unit/description detail checks → review page |
| `CommitteeSweep` | 08:00 | 10 municipalities (Complot+Bartech) → auto-rules → review page |

Order matters: `RefreshProjectsDB` must fully complete before the Mavat tasks read
`projects.db` — the 2026-07-19 atomic-rebuild fix protects this if the machine's clock catches
up late (e.g. after sleep) and tasks pile up close together.

## 9. Key files map

```
projects_monitor/
├── projects.db                      # built daily from the vault
├── scripts/refresh_db.py            # vault -> projects.db (atomic)
├── scripts/build_db.py              # stage vocab, date/number parsing (imported)
├── mavat_scraper/
│   ├── mavat_status.py              # low-level Mavat search/detail session (Playwright)
│   ├── mavat_diff.py                # MavatStatusDiff: vault-plan status diff + 106(ב) detection
│   ├── mavat_discover.py            # MavatDiscovery: nationwide new-plan sweep
│   ├── mavat_discover_units.py      # real unit counts + description-text signals
│   ├── auto_rules.py                # auto-exclusion rule engine (both sources)
│   ├── make_review_page.py          # builds mavat_review.html
│   ├── apply_review.py              # imports exported decisions, writes to vault
│   ├── mavat_discovery.db           # discovered candidates + vault-notice state
│   ├── mavat_state.db               # per-plan status snapshots + pending changes
│   └── mavat_review.html            # the daily review page
└── committee_scraper/
    ├── run_committee_sweep.py       # CommitteeSweep: municipality rotation + import + dedup
    └── committee_state.db           # committee candidates + per-muni rotation state
```

## 10. Gotchas worth knowing before you touch anything

- **A "0 tracked" or "0 candidates" log line is a red flag, not a quiet day** — it usually
  means a race with `RefreshProjectsDB`, or (for committee) a scraper output problem. Sanity-
  check against the historical baseline before assuming nothing happened.
- **`mavat_link`/`קישור למבאת` from committee scrapers is not proof a plan is on Mavat** — it's
  a templated search URL, not a confirmed match. Never re-introduce it as an exclusion signal.
- **Mavat's own status bucket hides sub-steps** — e.g. `הפקדה להתנגדויות/השגות` covers both an
  original deposit and a 106(ב) re-deposit after corrections. The real event detail lives in
  the plan's own stage-history log (`rsInternet` in the SV4 detail JSON), not the top-line
  status.
- **The 9-status whitelist is a hard gate**, not a display filter — a plan moving through any
  other status is invisible everywhere in this system, on purpose, to keep the review queue
  meaningful. If a real need shows up to track a 10th status, it must be added in all three
  places listed in §5 at once.

## Further reading

- `docs/framework_spec.md` — authoritative vault field/parsing spec.
- `docs/SCHEMAS.md` — full DB schema + the 33-code status vocabulary.
- `docs/MAVAT_AUTOMATION.md` — Mavat scraping findings, benchmarks, verdict history.
- `CLAUDE.md` — session-by-session history and the reasoning behind current decisions.
- `docs/BUG_REFERENCE.md` / `docs/VERSION_LOG.md` — known issues and change history.
