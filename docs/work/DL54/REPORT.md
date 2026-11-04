# DL54 report: delivery hook fixes

Status: in progress.

| Finding | Result | Evidence |
|---|---|---|
| F4 push HEAD | fixed | test_push_head_resolves_current_branch failed on main (joined, not pushed) |
| F5 PowerShell | fixed | test_powershell_push_is_recorded failed on main |
| F6 push --delete | fixed | test_push_delete_changes_nothing failed on main for --delete, -d, :name |
| Extra: gh pr create --head from another worktree | not reproduced | Two tests (existing train, unplanned train branch) with the shell cwd on `main` and `--head release/N` pass on current main: _rec_gh_pr already prefers the --head value. Tests kept. |
| F1, F3, F7, F8, F10 | pending | |

NOT READY
