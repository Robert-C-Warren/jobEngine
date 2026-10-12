@echo off
REM Autonomous Daily Job Engine Runner
cd /d "%~dp0"
echo ======================================================== >> daily_run.log
echo Running Daily Job Pipeline: %DATE% %TIME% >> daily_run.log
echo ======================================================== >> daily_run.log
.venv\Scripts\python.exe run_pipeline.py >> daily_run.log 2>&1
echo Completed at: %DATE% %TIME% >> daily_run.log
