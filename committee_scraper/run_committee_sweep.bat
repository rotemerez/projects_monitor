@echo off
rem Daily local-committee (Complot + Bartech) discovery rotation (scheduled task: CommitteeSweep).
rem Spreads the ~133 municipalities across ~10/day (~2 week/cycle) instead of one
rem weekly burst -- root cause of the 2026-06-24 outage (shared Complot backend
rem rate-limited under a full-133 blast). Bartech plans runs on Playwright (2026-07-13),
rem no ChromeDriver dependency.
cd /d C:\R_PROJECTS\projects_monitor
echo ===== run %date% %time% ===== > committee_scraper\committee_sweep_last.log
"C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe" -X utf8 committee_scraper\run_committee_sweep.py --count 10 >> committee_scraper\committee_sweep_last.log 2>&1
mavat_scraper\venv\Scripts\python.exe -X utf8 mavat_scraper\auto_rules.py --committee-only >> committee_scraper\committee_sweep_last.log 2>&1
"C:\Users\Rotem\AppData\Local\Programs\Python\Python313\python.exe" -X utf8 mavat_scraper\make_review_page.py >> committee_scraper\committee_sweep_last.log 2>&1
