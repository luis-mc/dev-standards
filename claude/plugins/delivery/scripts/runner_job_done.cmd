@echo off
rem ACTIONS_RUNNER_HOOK_JOB_COMPLETED hook for a self-hosted Windows runner (DL-90). See runner_job_done.py.
python "%~dp0runner_job_done.py" %*
if errorlevel 9009 py -3 "%~dp0runner_job_done.py" %*
exit /b %errorlevel%
