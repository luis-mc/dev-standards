#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_STARTED for a pool agent: take a machine CI slot (agent A's runner_load_gate).
exec python3 /opt/delivery/runner_load_gate.py "$@"
