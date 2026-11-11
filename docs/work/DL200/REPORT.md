# DL200 report

Base: origin/main 8915572; `queue_wait` present.

## Root cause
`test_dl194_pool_tool_cache.test_racing_fetches_end_with_one_good_file` patches `os.getpid` from two threads at once. The two `mock.patch.object` starts and stops can interleave, so `os.getpid` stays patched (1001 or 1002) for the rest of the process. The gate writes `gate_pid=os.getpid()` in its ticket. `queue_list` sees host equal and `pid_alive(1001)` false, calls the ticket dead and deletes it. The gate then sees an empty queue ("0 ahead in the queue") and waits for the real defaults (15 s poll, 30 min). Evidence: with a debug line in `queue_list`, a failing full run logged `DROP ... dead=True age=0.0007 pid=1001 host=vm/vm` for every ticket; the same run failed the first `test_machine` Gate tests. It happens in some full runs only (race), which is why it showed on some CI runs.

## What changed
- `runner_load_gate.queue_wait`: a missing own ticket is logged (`own ticket was gone; queued again (reason)`) and written again with the same queue time (a fresh time when it is older than `slot_stale_min`).
- `test_machine.machine()` now also pins `os.getpid` to the pid taken at import, so a leaked patch cannot kill the tickets. The `R.main` tests set `DELIVERY_GATE_MAX_WAIT_MIN=0.05` and `DELIVERY_GATE_POLL_SEC=0.01`.
- New `test_dl200_gate_vanished_ticket.py` (vanished ticket, leaked getpid).
- Spec: runner-pool R5.2 text, feature note `DL200.md`, change note `docs/architecture/changes/DL200-gate-vanished-ticket.md`.

## Tests
- test_machine alone: 67 OK in 1.5 s. test_load: 48 OK. New test: 2 OK.
- Full discover, 5 runs in a row: all OK, 70, 71, 69, 70, 72 s.
- Before the fix, one full run: 3 min hang (stack: `queue_wait` line 281 via `R.main` in the layer test); another: the Gate tests failed with 291 re-queues once the re-queue code was in and getpid was leaked.
- `tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed, 58 s.

## Follow-ups
- Fix `test_dl194_pool_tool_cache.py` (not mine to edit): patch `os.getpid` once with a per-thread `side_effect`, not from two threads. Until then other tests that use `os.getpid` can be hit.
- docs_check W1 (work report on branch) is expected until the strip before the join.

## CI (spec-lint, areas=delivery,docs, run 42993102814, head 8c3de64)
Run ended: failure, only the `docs check` job (0 s: the W1 rule, a work report on the branch; expected, see Follow-ups). Every other job passed or was skipped.
- delivery - plugin ledger, recorder, watcher and hooks: success, 52 s (the job that hung before).
- delivery - CI scripts and workflow templates: success, 78 s. packaged-program smoke test: success, 74 s. train cleanup: success, 35 s. change notes enforced and folded: success, 17 s. runner plan: success, 10 s. area mapping: success, 7 s. setup preflight: success, 5 s. branch gate and trust rule: success. artifact pruning: success.
- docs plugin: success, 46 s. which areas: success. docs check: failure (W1 only). change notes, change notes folded, specs/templates, artifact renderer, shard job, model profiles, transcript folds: skipped.

Branch head: see the git log (this report is committed after the run).

READY
