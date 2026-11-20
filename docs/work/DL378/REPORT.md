# DL378 report: ci_watch lets a red run finish

## Change
- `ci_watch.cancel_on_red` default is now false (D105, DL-97). On the first failed job ci_watch prints it at once, waits for every job of the head's runs, then prints every failed job with its failed steps and exits 1.
- `cancel_on_red: true` or `--cancel-on-red` cancels only a train head whose failed job or step matches `ci_watch.blocking_job_re` (default `setup|install|lockfile|build|checkout`). Any other failure warns that D105 keeps the run going, and waits.
- The push freeze reads the live runs, so it lifts when the runs complete or the cancelled runs end. No code change was needed there.

## Files
- claude/plugins/delivery/templates/shared/scripts/delivery/ci_watch.py (docstring, default, blocking check, `--cancel-on-red`)
- claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md (ci_watch paragraph)
- claude/plugins/delivery/tests/test_dl378_ci_watch_red_finishes.py (new, 8 cases)
- claude/plugins/delivery/tests/test_dl306_red_run_cancel.py (updated: the failing job is now `build-rust`, a blocking name; the config default is asserted false)
- docs/features/delivery-speed/spec.md (R5.22 and its test row)
- docs/features/delivery-speed/changes/DL378.md, docs/architecture/changes/DL378-ci-watch-red-finishes.md (change notes)

## Tests (run from claude/plugins/delivery/tests with `python3 -m unittest`)
- test_dl378_ci_watch_red_finishes, test_dl306_red_run_cancel: 18 tests, OK
- test_dl247_ci_watch_give_up, test_ci_options, test_dl127_ci_watch_ledger, test_dl183_rerun_first_pending, test_dl226_agent_ci_path_ci_watch, test_dl336_ci_watch_default_head, test_dl235_ci_watch_quota, test_dl374_red_run_finishes, test_dl96_watcher_rearm, test_dl118_rearm_unstoppable: all OK
- No delivery-gate case uses ci_watch, so none was run. No Docker, no mutation passes.

## docs_check
2 errors, neither from this change:
- W1: docs/work/DL378/REPORT.md is a work file on this branch (expected, never reaches main).
- G1: docs/architecture/decisions.md is stale (generated file, not edited here, as AGENTS.md forbids).
The T2 date check was not run (shallow clone).

READY
