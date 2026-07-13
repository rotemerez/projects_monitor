@echo off
rem Nightly Mavat status diff (scheduled task: MavatStatusDiff).
rem Checks the 300 least-recently-checked active tracked plans; report -> ..\mavat_report.md
cd /d C:\R_PROJECTS\projects_monitor\mavat_scraper
set PYTHONUTF8=1
echo ===== run %date% %time% ===== > status_diff_last.log
venv\Scripts\python.exe -u mavat_diff.py --rotate 300 --details 25 --report ..\mavat_report.md >> status_diff_last.log 2>&1
venv\Scripts\python.exe -u make_changes_page.py >> status_diff_last.log 2>&1
