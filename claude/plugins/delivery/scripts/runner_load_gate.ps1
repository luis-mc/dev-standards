# ACTIONS_RUNNER_HOOK_JOB_STARTED hook for a self-hosted Windows runner (DL-79). See runner_load_gate.py.
$py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }
& $py (Join-Path $PSScriptRoot 'runner_load_gate.py') @args
exit $LASTEXITCODE
