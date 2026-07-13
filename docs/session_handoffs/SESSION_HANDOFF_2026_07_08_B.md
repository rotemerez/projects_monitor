# Session Handoff — 2026-07-08 B (start here / next-session prompt)

**Date:** 2026-07-08
**Project root:** `C:\R_PROJECTS\projects_monitor`

This project was relocated in two steps on 2026-07-08:
1. Renamed `projects_export` → `projects_monitor` (done by **copying** on the Desktop, because
   the folder couldn't be renamed while VSCode held it open).
2. Then **moved** `C:\Users\Rotem\Desktop\projects_monitor` → `C:\R_PROJECTS\projects_monitor`.

Everything now lives in, and points at, `C:\R_PROJECTS\projects_monitor` — the scheduled task,
the docs, and a freshly recreated scraper venv were all updated and verified. The **original
`C:\Users\Rotem\Desktop\projects_export` folder still exists as inert leftovers** and should be
deleted.

---

## FIRST ACTION — delete the OLD Desktop folder

The folder to delete is **`C:\Users\Rotem\Desktop\projects_export`** (the original). Nothing
points at it anymore, so deleting it loses nothing. It just needs to not be held open by any
process.

> Do NOT delete `C:\R_PROJECTS\projects_monitor` — that is the live project.

1. Make sure you are working out of the **new** folder: this VSCode window / Claude session
   should be open on `C:\R_PROJECTS\projects_monitor`.
2. Make sure nothing else holds the old folder: no terminal `cd`'d into it, no File Explorer
   window open on it, and it is not the open folder in any other editor (the previous session had
   it open in VSCode — that lock is what blocked deleting it earlier).
3. From a terminal that is **not** inside the old folder, run:
   ```powershell
   Remove-Item 'C:\Users\Rotem\Desktop\projects_export' -Recurse -Force
   ```
4. Verify it's gone:
   ```powershell
   Test-Path 'C:\Users\Rotem\Desktop\projects_export'   # should print False
   ```

**If you get "The process cannot access the file because it is being used by another process":**
something still holds it open. Close any terminal/Explorer/editor pointing at it and retry. To
find the holder if needed:
```powershell
# lists processes whose path mentions the old folder
Get-Process | Where-Object { $_.Path -like '*Desktop\projects_export*' } | Select-Object Name, Id, Path
```

---

## Confirm the migration is intact (quick checks)

```powershell
# 1) Scheduled task points at the new location
(Get-ScheduledTask -TaskName RefreshProjectsDB).Actions.Arguments
#   -> should contain C:\R_PROJECTS\projects_monitor\scripts\refresh_db.py and ...\projects.db

# 2) Scraper venv works (headless lookup)
$env:PYTHONUTF8=1
$vpy = "C:\R_PROJECTS\projects_monitor\mavat_scraper\venv\Scripts\python.exe"
& $vpy "C:\R_PROJECTS\projects_monitor\mavat_scraper\mavat_status.py" --headless 457-1253954
#   -> [OK ] 457-1253954  אישור  ...
```

The daily `RefreshProjectsDB` task (06:00) already targets the new folder, so no task action is
needed beyond confirming the above.

---

## Where things stand

- **Vault -> DB pipeline**: working, scheduled. `scripts/refresh_db.py` builds all 5 tables of
  `projects.db` (`projects` ~10,516, `status_events` ~12,026 with `is_current`, `tenders`,
  `signatures`, `value_history`).
- **Mavat scraper** (`mavat_scraper/mavat_status.py`): headless works; search-only extraction of
  status + code + date per plan. Verified after the move.
- **Observed 2026-07-08**: the same plan (`457-1253954`) intermittently returned a `MISS` on one
  warm lookup, then matched on immediate re-run — live-site flakiness, not a code/path issue.
  (See retry item below.) Its `status_code`/date also shifted between runs while the label stayed
  `אישור`, confirming `status_code` is a secondary signal.

## Next steps (parked until now)

1. **Scraper hardening** (`mavat_scraper/`):
   - **Concurrency re-run** — `conc_test.py` (async route handler was fixed; needs a clean run to
     read real parallel throughput and WAF/IP behavior).
   - **Retry a miss once** — a MISS was observed to be transient; re-query a missed plan once (short
     backoff) before recording it as a real miss, to avoid false "not found"s in the daily run.
   - **Polite rate-limiting** — inter-request delay, low concurrency, before any full run.
2. **Wire the daily diff** — for each `plan_current`, look up Mavat and compare vs.
   `status_events.is_current`; emit a change report (separate layer, not written back into the
   vault). Treat status label + date as the primary change signal; `status_code` is secondary.
3. **Map** Mavat status codes/labels onto the 33-code `STAGE_LABEL` vocabulary in
   `scripts/build_db.py`.
4. **New-plan discovery** — first review the separate `C:\R_PROJECTS\local_committee_scrapers`
   and `C:\R_PROJECTS\projects_file_download` projects (their own scheduled tasks) before
   duplicating.

See `README.md`, `next_steps.md`, `CLAUDE.md`, and `docs/` for full detail.
