#!/bin/sh
# ACTIONS_RUNNER_HOOK_JOB_STARTED for a pool agent: take a machine CI slot (agent A's runner_load_gate).
# A job may have put another python first on PATH (actions/setup-python) with its own library path, so the hook
# runs the image's interpreter by absolute path with the job's python variables cleared (DL81).
# DL87: a job starts and ends with a clean temp space. Hosted runners give every job a fresh /tmp; the pool
# shares one, and some actions hard-code /tmp. Empty this agent's own temp folder, then delete the top-level
# /tmp entries this user owns. rm -rf acts on the entries (no symlink is followed); find has no -L. Never fails the job.
clean_tmp() {
  case "${TMPDIR:-}" in
    /agents/*) [ -d "$TMPDIR" ] && find "$TMPDIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} + || true ;;
  esac
  find /tmp -mindepth 1 -maxdepth 1 -user "$(id -u)" -exec rm -rf {} + || true
}
clean_tmp
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec /usr/bin/python3 /opt/delivery/runner_load_gate.py "$@"
