#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_STARTED for a pool agent: take a machine CI slot (agent A's runner_load_gate).
# A job may have put another python first on PATH (actions/setup-python) with its own library path, so the hook
# runs the image's interpreter by absolute path with the job's python variables cleared (DL81).
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec /usr/bin/python3 /opt/delivery/runner_load_gate.py "$@"
