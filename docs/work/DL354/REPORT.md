# DL354 report

Fix: a container recreate counts only runners in the pool container (R5.59).

## Files
- claude/plugins/delivery/scripts/delivery_runner_pool.py (pool_scope, scan_pool_runners, scope_text; runners_busy, apply_cap, drain_and_recreate)
- claude/plugins/delivery/tests/test_dl354_swap_busy_scope.py (new); test_dl92_pool_fixes.py (fixture runner now has a name)
- docs/features/runner-pool/spec.md (R5.59, test row); docs/features/runner-pool/changes/DL354.md
- docs/architecture/changes/DL354-swap-busy-container.md

## Tests
- python3 -m unittest test_dl354_swap_busy_scope test_runner_pool test_dl289_refresh_drain test_dl92_pool_fixes test_dl341_pool_all_oses test_dl343_kvm_autoload test_dl149_pool_layers test_dl162_pool_refresh_files test_dl103_pool_keep_cap test_dl165_pool_refresh_hash_result: 280 tests OK
- docs_check.py: M1 on delivery spec cleared by the commit's Docs line (check with full history in CI)

Code commit: 873d1f5 (final branch head is in the push output)

READY
