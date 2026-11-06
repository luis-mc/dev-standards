#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_COMPLETED for a pool agent: free the slot and clean _work (agent A's runner_job_done).
# A job may have put another python first on PATH (actions/setup-python) with its own library path, so the hook
# runs the image's interpreter by absolute path with the job's python variables cleared (DL81).
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec /usr/bin/python3 /opt/delivery/runner_job_done.py "$@"
