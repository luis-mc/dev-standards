#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_COMPLETED hook for a self-hosted Linux/macOS runner (DL-90). See runner_job_done.py.
d=$(dirname "$0")
if command -v python3 >/dev/null 2>&1; then exec python3 "$d/runner_job_done.py" "$@"; fi
exec python "$d/runner_job_done.py" "$@"
