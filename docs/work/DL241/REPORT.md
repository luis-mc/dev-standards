# DL241 report: join sibling branches

Base check: `join.py` has `def stacked_on_older` on origin/main. OK.

## Reproduction
Temp repo with a bare remote: `contract` off main, then A, B, C off `contract`. Before the fix, `join.py A B C` stopped B with "B is stacked on an older A" and an empty file list, because the old check only asked whether the merge base was outside the integration head. The shared contract commit passed that test.

## What changed (join.py, R5.56)
- `stacked_on_older` returns `(A, files)`. It reports stacked only when the merge base is not in the integration head, is not the tip of a remote branch outside the call (a contract branch), and the files A's old work touched and A rewrote later are not empty. It never returns an empty list.
- The stacked stop prints `join: files in both: ...`.
- Every skipped branch prints `skipped <branch>: <reason>` (conflict with files, stacked with files, not ready / no trusted gate result, missing on remote, not reached). Printed with or without `--push`.
- A partial join ends with `joined N of M branches; skipped: <names>`.
- Exit codes: conflict or stacked stays 3; gate refusal keeps its code; new code 5 = a branch missing on the remote. `--allow-partial` makes the 3 and 5 cases exit 0 and still prints the summary. A gate refusal is not softened.
- A branch missing on the remote used to fail at the gate or at the merge; it is now skipped and named.
- Spec R5.56, feature note `docs/features/delivery/changes/DL241.md`, change note `docs/architecture/changes/DL241-join-sibling-branches.md`.

## Tests
- `python3 -m unittest tests.test_dl241_join_siblings tests.test_dl128_join_fixes tests.test_dl111_join_keeps_clean tests.test_dl225_join_peer_fixes tests.test_dl99_join_fresh_branches tests.test_dl197_join_keeps_base_docs_work` (run in claude/plugins/delivery): 30 tests, OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: G1 (decisions.md stale, also on origin/main in a shallow clone) and W1 (this report). M1 on delivery-speed is answered by `Docs: none` in the commit message.
- `spec-lint.yml --ref DL241-join-sibling-branches -f areas=delivery`, two runs (43085668455, 43086024572). Both ended: `docs check` failed on G1 and W1; the delivery suite jobs (branch gate, train cleanup, CI scripts, change notes, artifact pruning, ledger/hooks, smoke) were cancelled by that failure and never ran; area mapping, runner plan, setup preflight, which-areas passed; the roll-up job failed. The delivery suites did not run in CI because of G1 and W1 alone; local results above stand in.

## Follow-ups
- delivery-speed spec maps join.py; it needs no text change.
- G1 on main needs `docs_index.py build` by the docs owner.
- The new `--allow-partial` flag and exit 5 may need a line in any skill text that lists join exit codes.

READY
