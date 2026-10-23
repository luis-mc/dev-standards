@echo off
rem ACTIONS_RUNNER_HOOK_JOB_STARTED hook for a self-hosted Windows runner (DL-79). See runner_load_gate.py.
python "%~dp0runner_load_gate.py" %*
if errorlevel 9009 py -3 "%~dp0runner_load_gate.py" %*
exit /b %errorlevel%
