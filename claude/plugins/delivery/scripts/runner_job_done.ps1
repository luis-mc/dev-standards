# ACTIONS_RUNNER_HOOK_JOB_COMPLETED hook for a self-hosted Windows runner (DL-90). See runner_job_done.py.
$py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }
& $py (Join-Path $PSScriptRoot 'runner_job_done.py') @args
exit $LASTEXITCODE
