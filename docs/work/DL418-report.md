# DL418 report

READY. Branch DL418-runner-out (local work branch dl418-work, rebased on origin/main b92af115, no conflicts).

Fixed on top of the WIP: hook_stop.py read ledger jobs[] (KeyError; broke test_recording); removed pool-refresh from delivery_eta.py; added DL-50 and DL-51 to docs_check REMOVED_DELIVERY_IDS, the removed-ids guide and test_ds246; renamed a test; notes for docs plugin, features/docs and features/test-cost.

Kept on purpose: runner_plan.cancel_replaced_runs and hold_dependabot_during_train (they act on CI runs), config runners list.

Tests:
- delivery plugin tests: 1354 run, 15 failures, 4 errors before the hook_stop fix. Everything else is the same on main (gitleaks, bash, Linux, chromium, encoding on Windows). test_recording now passes.
- tools: delivery_ci watch queued cases pass (3); delivery_gate freeze 21 checks, quick 27 checks, 0 failed.
- test_ds246_removed_ids 6 OK. change_notes check ok.
- docs_check: only W1 (docs/work, branch-only) and G1 (generated index stale, rebuilt at join); no other errors in my files.
