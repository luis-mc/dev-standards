# CO427 report: Needs you vs Waiting for other work

Branch `claude/CO427-needs-you-vs-waiting`. Status: started.

## Plan
- The only "Waiting or on hold" section is the At a glance group `waiting` (R5.34). Split it: tasks whose wait is on the owner join the `you` group (Needs you); the rest stay in `waiting`, relabelled "Waiting for other work".
- The record has no owner-vs-work signal (no Blocked status; `expected_basis`/`detail` are free text), so add the smallest optional field: `waits_on` = `owner|work` on a task, set with `--waits-on` on `task-add` and `set-task-status`; absent means `work` (old behaviour).
- Rows of both groups read dependency first (from `expected_basis`, else the release it rides, else the first sentence of `detail`), then the item, then Expected.
- Versions by change note (this repo forbids version edits off integration branches).
