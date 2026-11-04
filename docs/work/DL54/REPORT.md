# DL54 report: delivery hook fixes

Status: in progress.

| Finding | Result | Evidence |
|---|---|---|
| F4 push HEAD | fixed | test_push_head_resolves_current_branch failed on main (joined, not pushed) |
| F5 PowerShell | fixed | test_powershell_push_is_recorded failed on main |
| F6 push --delete | fixed | test_push_delete_changes_nothing failed on main for --delete, -d, :name |
| Extra: gh pr create --head from another worktree | not reproduced | Two tests (existing train, unplanned train branch) with the shell cwd on `main` and `--head release/N` pass on current main: _rec_gh_pr already prefers the --head value. Tests kept. |
| F3 ~HH:MM and owner zone | fixed | test_tilde_time_is_read, test_bare_date_ends_at_local_midnight, test_time_is_read_in_owner_zone, test_registry_uses_cfg_tz failed on main |
| F8 stalled and pushed agents | fixed | test_stalled_and_pushed_agents_are_checked failed on main for stalled and pushed |
| F10 year wrap | fixed | test_year_wraps_forward_in_december failed on main (the January-back case already passed) |
| F1, F7 | pending | |

NOT READY
