#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_STARTED hook for a self-hosted Linux/macOS runner (DL-79). See runner_load_gate.py.
d=$(dirname "$0")
if command -v python3 >/dev/null 2>&1; then exec python3 "$d/runner_load_gate.py" "$@"; fi
exec python "$d/runner_load_gate.py" "$@"
