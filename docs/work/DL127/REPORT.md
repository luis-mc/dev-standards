# DL127 report

Branch: DL127-ci-watch-ledger. Code head: a641f8aca442831f5009be02eb286b9533fe5feb (the report commit follows it).

## What changed
- DL127 (`delivery_ledger.py`):
  - `agent-check <agent or task>` sets `last_checked` on an open agent and adds an `agent.checked` event.
  - New `record` op `agents_done(pr, branches, tasks)`: closes (done/ready) open agents whose task is in the train's cargo or whose branch is in the list.
  - `show` prints "open agents whose task the project record shows as finished" for tasks whose row in `docs/project/*.html` (a `<tr data-task=...>` with a `status-chip status-live|dropped|built`) is closed. Read defensively; never raises. Helpers: `project_statuses`, `stale_agents`.
- DL127 (`cleanup.py`, close-agents step only): after a clean `--pr N` run, calls `agents_done` with the train's branches.
- DL132 (`ci_watch.py`): `ledger_root()` uses `git rev-parse --git-common-dir`; when it is a `.git` whose parent holds `.delivery/`, that main checkout is the ledger root. Else the old repo root.
- DL138: `ci_watch.py` `head_of(sha)` finds the branch at the commit (git only, local then remote, not main/master). `ledger_ci` passes `branch`, `pr`, `create=True`. `record("ci")` matches by train, PR, branch, then head sha; with none and a branch it creates the train (as `plan --branch`) in state `ci`. With no branch it records `ci.unmatched` and prints `delivery_ledger.py plan --branch <branch>` to stderr. `plan --branch` returns the open train of that branch instead of a duplicate. `find_train` matches PR first.
- DL139 (`ci_watch.py`): once the named workflow's runs are complete, one unfiltered `gh run list --commit <sha>` adds every other workflow's run. Any pending one keeps the watch waiting; any failed one exits 1. `--only-workflow` keeps the old watch. A failed unfiltered read prints one warning and the named runs decide.

## Exact behaviour for the spec
See the lines above and `docs/architecture/changes/DL127-ci-watch-ledger.md`. Not touched (not owned): `scripts/hook_session_start.py`; its check-in summary could call `delivery_ledger.stale_agents(root, ledger)` to name the same agents.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl127_ci_watch_ledger`: 10 tests OK.
- `python3 -m unittest test_ledger test_ledger_root_worktree test_ci_runs test_dl121_port_fixes test_dl115_ci_tool test_dl96_ledger_ids test_dl127_ci_watch_ledger`: 114 OK.
- Named cases of `tools/test_delivery_ci.py` (watch_*, run through a small loader, not the full suite): 36 of 39 pass. 3 fail, as the extra call changes the fake gh's call sequence:
  - `watch_waits_when_no_run_exists_yet` (expects 3 `run list` calls, now 4 on the deciding poll),
  - `watch_waits_while_a_run_is_in_progress`,
  - `watch_pr_head_push_skipped_and_pr_queued_keeps_waiting` (fixture has no run 2 for the extra call).
  These cases live in `tools/test_delivery_ci.py`, which this task does not own. They need fixture updates (the deciding poll makes one more `run list` call).
- `gh workflow run spec-lint.yml --ref DL127-ci-watch-ledger -f areas=delivery`: run 42656718666 failed: delivery-ci 74/75 passed, the 3 cases above (the first run, 42655366970, also failed on 4 cases before the fix). Every other suite in that run passed or was skipped.
- `python3 claude/plugins/docs/scripts/docs_check.py`: G1/W1 expected (W1 is this report). Also M1 on `docs/features/delivery/spec.md` and `docs/features/delivery-speed/spec.md`: the feature spec text is for the orchestrator. T2 warnings only.

## Fix round
- Cause: DL139 adds one unfiltered `gh run list --commit` after the named workflow's runs are complete. The fake gh in `tools/test_delivery_ci.py` advanced its fixture sequence on every `run list`, so that extra call used up a poll.
- Change (test side only; `ci_watch.py` untouched): the fake gh now only peeks at the current poll for a `run list` with no `--workflow`. Named-workflow reads still advance the sequence. The three cases count only `--workflow` polls, so each still proves its wait count (3, 2, 3).
  - Why not skip the read in `ci_watch.py`: the read is the DL139 behaviour and runs only when the named runs are complete, so it should stay.
- `watch_*` cases of `tools/test_delivery_ci.py` (loader): 39 of 39 pass.
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl127_ci_watch_ledger`: 10 tests OK.
- `gh workflow run spec-lint.yml --ref DL127-ci-watch-ledger -f areas=delivery`: run 42665100724, completed, failure only from "docs check" (M1 and W1, expected). Delivery jobs, all success: smoke test, runner plan, setup preflight, CI scripts and workflow templates, train cleanup, change notes enforced and folded, artifact pruning, branch gate and trust rule, area mapping, plugin ledger/recorder/watcher/hooks, delivery scripts/CI templates/cleanup/prune/change notes. Other areas skipped.
- Fix commit: c99329d20437cd4c64e880336a7bd8bc4c065f68 (the report commit follows it).

READY
