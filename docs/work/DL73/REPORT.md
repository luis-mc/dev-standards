# DL73 report

## Cause
Two test races in the fake program, not in smoke_packaged.py.
1. The fake program wrote its own pid after it printed `api ready` and started the workers. The smoke could stop the tree before that write.
2. `sc_stop_tree` waited only for `worker-mail ready`. The queue worker is started first but can still be starting then. The smoke stopped the tree and the queue worker never wrote its pid (seen locally as 2 pids, 9 of 30 runs failed).

Polling would not help: a stopped process never writes its pid.

## Fix (tools/test_smoke_packaged.py only)
- The fake program writes its pid first, before it prints anything.
- `sc_stop_tree` expects both `worker-queue ready` and `worker-mail ready`.
The `>= 3 pids` check, the timeout and the stop check are unchanged. smoke_packaged.py is not changed: no product bug found. No change note needed (commit says `Docs: none, test-only race fix`).

## Results
- Loop: 30 of 30 passed after the fix (21 of 30 with only the first part of the fix).
  Command: `run_suite.py smoke-packaged stop_tree` x30 (runs `tools/test_smoke_packaged.py --no-mutants -k stop_tree`).
- Full file with --no-mutants: NOT run. The session guard hook refuses a full local run of the heavy smoke-packaged suite and says to leave it to CI.
- `python3 tools/ci_areas.py --branch-advice`: heavy: delivery -> `gh workflow run spec-lint.yml --ref DL73-smoke-pid-wait -f areas=delivery`. Not run (heavy, and no gh here). Please run it in CI.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, W1 (docs/work/DL73/REPORT.md, expected on a branch). Nothing else.

Head SHA: see the branch head on origin (the last commit on DL73-smoke-pid-wait).

NOT READY
