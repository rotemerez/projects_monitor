@echo off
rem Weekly Mavat new-plan discovery sweep (scheduled task: MavatDiscovery).
rem Sweeps status changes since the last sweep, applies auto-rules, regenerates the review page.
cd /d C:\R_PROJECTS\projects_monitor\mavat_scraper
set PYTHONUTF8=1
echo ===== run %date% %time% ===== > discovery_last.log
venv\Scripts\python.exe -u mavat_discover.py >> discovery_last.log 2>&1
venv\Scripts\python.exe -u auto_rules.py --units-rule >> discovery_last.log 2>&1
venv\Scripts\python.exe -u make_review_page.py >> discovery_last.log 2>&1
