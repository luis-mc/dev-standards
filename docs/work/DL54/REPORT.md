# DL54 report: delivery hook fixes

Status: done.

| Finding | Result | Evidence |
|---|---|---|
| F4 push HEAD | fixed | test_push_head_resolves_current_branch failed on main (joined, not pushed) |
| F5 PowerShell | fixed | test_powershell_push_is_recorded failed on main |
| F6 push --delete | fixed | test_push_delete_changes_nothing failed on main for --delete, -d, :name |
| Extra: gh pr create --head from another worktree | not reproduced | Two tests (existing train, unplanned train branch) with the shell cwd on `main` and `--head release/N` pass on current main: _rec_gh_pr already prefers the --head value. Tests kept. |
| F3 ~HH:MM and owner zone | fixed | test_tilde_time_is_read, test_bare_date_ends_at_local_midnight, test_time_is_read_in_owner_zone, test_registry_uses_cfg_tz failed on main |
| F8 stalled and pushed agents | fixed | test_stalled_and_pushed_agents_are_checked failed on main for stalled and pushed |
| F10 year wrap | fixed | test_year_wraps_forward_in_december failed on main (the January-back case already passed) |
| F1 hooks.json fallback | fixed | test_block_exit_code_survives ran the real PreToolUse command with DELIVERY_LOAD=99,99: exit 0 on main, exit 2 now. All 6 commands use `if command -v python3 ...; then python3 X; else python X; fi`. tools/test_delivery_hooks.py wiring assert updated. |
| F7 DL-91 pid | fixed | test_heavy_call_survives_its_hook_shell failed on main (record dropped at once). heavy_begin now stores no pid or host; heavy_end or slot_stale_min removes it. test_machine's dead-pid test now writes an old-style record with pid and host. |

## Tests

- Delivery suite (`python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`): 595 tests, OK.
- tools/test_delivery_hooks.py: not run. The session guard refused it as a heavy suite with no local measurement; PR CI runs it. I changed one line there (the hooks.json wiring assert).
- docs_check.py: M1 for features/delivery and delivery-speed (answered by the `Docs: none` commit line), W1 for this report (stays on the branch, D9).

## Notes

- Change note: docs/architecture/changes/DL54-delivery-hook-fixes.md. No spec text changed.
- Files outside my list touched: claude/plugins/delivery/tests/test_machine.py (one old test encoded the dead-pid drop).

branch head SHA: see the last commit on origin/DL54-delivery-hook-fixes

READY
