# DL111 report

## What changed
- `join.py`: a conflict (not lockfile-only), a failed lockfile resolve or commit no longer returns. It aborts that merge, records the branch with its conflict files, and goes on with the next branch.
- New `finish_partial()` runs after the loop when any branch conflicted or was refused.
- New test `claude/plugins/delivery/tests/test_dl111_join_keeps_clean.py`; change note `docs/architecture/changes/DL111-join-keeps-clean-merges.md`.

## Exact behaviour (for the spec)
- Flags are unchanged: `join.py --into INTEGRATION [--ci-gate] [--no-gate] [--push] A B C`.
- Every branch is tried. Clean merges stay; each conflicting branch is skipped.
- stderr: per conflicting branch `join: X conflicts with INTEGRATION in:` and its files, one per line.
- With `--push`: pushes INTEGRATION (same `git push --no-verify` as a full success), then stderr `join: kept the clean merges (A, B) and pushed INTEGRATION; the other branches are left to do`, exit 3 (EXIT_CONFLICT). Ledger: `cargo` for each joined branch and `train_state pushed`; no `joined` state.
- Without `--push`: stderr `join: kept the clean merges (A, B), committed on local INTEGRATION; not pushed (no --push)`, exit 3. Nothing is discarded.
- No clean merge: `join: no branch merged cleanly; nothing kept`, exit 3.
- Push failure on a partial join: exit 1, clean merges stay committed locally.
- `.delivery/join-result.json` on a partial join: `joined`, `stopped_at` (first problem branch), `conflicts` (flat file list, as before), plus `conflicting` (`{branch: [files]}`), `partial: true`, `pushed`, `skipped_steps`, and `refused` (`{branch, reason}`) when a refusal stopped the join.
- Gate refusal (no trusted gate, not ci_gate): stops at once, keeps and reports earlier clean merges the same way, exits with the refusal's own code. A plain `git merge` failure with no conflict files stops the same way with exit 2.
- Lockfile-only conflicts: unchanged (take INTEGRATION's version, re-run setup, commit).
- Steps after the merges (docs stripping, gallery rebuild, light check, ready PR text) do NOT run on a partial join. They judge the whole head, and the head is not whole. The call that joins the rest runs them on the full head. The strip step only removes files, so the later run still removes briefs and reports that a partial push carried.
- All-clean join: unchanged.

## Tests
- `python3 claude/plugins/delivery/tests/test_dl111_join_keeps_clean.py`: 4 tests OK (A,B clean + C conflict with --push; A,C,B; no --push keeps local; all clean).
- `python3 claude/plugins/delivery/tests/test_dl99_join_fresh_branches.py`: 5 tests OK.
- `run_suite.py delivery-gate join` (join scenarios of tools/test_delivery_gate.py; the full file is refused locally as a heavy suite): 99 checks, 0 failed.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (local branch not on remote yet); advises `gh workflow run spec-lint.yml --ref DL111-join-keeps-clean-merges -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`. Not run (no gh here).
- `docs_check.py` not run: the luismc-docs plugin path is not available here.

## Head
See `git rev-parse origin/DL111-join-keeps-clean-merges`.

READY
