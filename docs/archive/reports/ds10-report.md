# DS10 report: luismc-delivery hook fixes

Seen in a real project on 17 Oct (20:40-22:50). Three fixes in `claude/plugins/delivery/scripts`, each with a test.

1. **DL-14 / DL-18 and holds** (`hook_stop.py`): a merged train with an active hold (`delivery_ledger.py hold --by rule --until ISO`) no longer triggers either rule; once `until` passes they apply again. Test: `dl14_dl18_hold_suppresses_until_it_lapses`.
2. **ci_watch recorder** (`hook_post_tool.py`): a `run_in_background` start records nothing; a foreground exit 0 records only with the "succeeded" output. Test: `test_ci_watch_started_in_background_records_nothing`.
3. **DL-06 cross-repo** (`hook_pre_tool.py`): `--repo` is passed to `gh pr view`; trains carrying that repo (`repo` field) are matched against it, and a repo that is not the current one and that no train carries is skipped. Test: `dl06_cross_repo_pr_is_not_judged_by_the_current_repos_pr`.

Version: change note `DS10-delivery-hook-fixes.md` (patch); the fold bumps `plugin.json`.

Checks: touched cases of `tools/test_delivery_hooks.py` run by name, plus `test_post_tool` and `test_stop` in the plugin's tests. Full suite left to CI.
