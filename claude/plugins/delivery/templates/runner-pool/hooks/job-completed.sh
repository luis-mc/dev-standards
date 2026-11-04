#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_COMPLETED for a pool agent: free the slot and clean _work (agent A's runner_job_done).
exec python3 /opt/delivery/runner_job_done.py "$@"
