# DL128 report

## Changes (join.py)
- DL128: a branch B that contains an older head of another branch A of the same call (A's head not in B, merge-base on A's side only, via git merge-base --is-ancestor) is skipped. stderr: `join: B is stacked on an older A; prefer B's side for files B rewrote`, then `merge B alone ... or rebase B on the current A`. It is reported as conflicting with no files; exit 3. If B carries A's whole head, B merges normally.
- DL129: new flag `--create`. Without it, a missing `--into X` fails (exit 2) with: `integration branch 'X' not found on remote 'origin'; run again with --create, or create it: git push origin origin/<default>:refs/heads/X`. With it the join pushes origin/<default> as X, prints `join: created X on origin from origin/<default>`, goes on.
- DL135: when the light check fails and a log under the join log dir holds "unhandled API call" (any case), stderr and join-result.json `quick_check.join_interaction` carry: `join-interaction failure: the e2e teardown reports an api-mock 'unhandled API call'. Each branch passed alone; a call one branch added is not mocked by another branch's test. ...`.
- DL140: after the light check, before runner health/push: `pre_pr_docs` runs design_system.py visuals --apply (only if docs/design-system/next-version exists), docs_index.py build (commits docs changes as "Rebuild generated docs"), docs_check.py --strict; lists T2 specs under "specs with T2 findings, verify before push:". A missing script prints `luismc-docs X not found; ... skipped`. Result in join-result.json `pre_pr_docs`. Never blocks. Note: design_system.py `visuals` takes `--apply` but ignores it; it always writes.
- DL145: when local INTEGRATION is ahead of origin/INTEGRATION the join builds on it (`join: local X is ahead of origin/X; building on the local branch`). When local has commits not in origin and origin is not built on them, it refuses (exit 2): `... joining would lose them. Push or rebase local X first.` Conflicts under docs/work/ take the branch's side (`... took the branch's side of ... under docs/work/`).
- Existing flags and output lines are unchanged.

## Tests
- python3 claude/plugins/delivery/tests/test_dl128_join_fixes.py: 7 tests OK
- unittest test_dl99_join_fresh_branches + test_dl111_join_keeps_clean: 9 OK
- python3 tools/ci_areas.py --branch-advice: "heavy: unreadable diff" (uncommitted at the time); spec-lint dispatch: see below.
- python3 claude/plugins/docs/scripts/docs_check.py: only M1 for docs/features/delivery/spec.md and docs/features/delivery-speed/spec.md (spec text is left to the orchestrator; the change note names the plugin only). No G1/W1 seen.
- gh workflow run spec-lint.yml --ref DL128-join-fixes -f areas=delivery: dispatched, run https://github.com/luis-mc/dev-standards/actions/runs/42654360882 (result not awaited; check it).

Code head: fc61e3d799aa94dbe47288fd1c7736293bfe9580 (this report commit follows it).

## Fix round
CI run 42654360882 failed 6 checks in `delivery - branch gate and trust rule`.

Cause:
- 3 join_same_tree checks: the DL140 step printed "luismc-docs X not found; ... skipped". The tests look for the word "skipped" in the output to tell a skipped gate, so they matched the docs line.
- join_docs_strip "removal is its own commit": with the docs plugin present, DL140 commits "Rebuild generated docs" after the strip, so the last commit is no longer the strip.
- 2 join_conflicts checks: the first join in the box stays local and ahead of origin. DL145 builds the next join on it, so the second join found nothing to conflict.

Change:
- join.py: the absent-script line now says "not run" instead of "skipped". The gate and the exit code are untouched (the docs step runs after the gate and only prints).
- test_delivery_gate.py, two expectations changed because DL140 and DL145 require the new behaviour: (1) the strip commit is checked among the last commits, as DL140 may add a rebuild commit after it; (2) the lockfile-with-failing-setup case resets local integ to origin/integ before the second join, as DL145 keeps unpushed local joins.
- test_dl128_join_fixes.py: new test_pre_pr_docs_never_changes_exit. Failing docs scripts and absent docs scripts both give exit 0, the join result lists the failure, and the output has no "skipped".

Tests:
- python3 tools/test_delivery_gate.py --no-mutants -k join_: 99 checks, 0 failed (was 6 failed).
- python3 claude/plugins/delivery/tests/test_dl128_join_fixes.py: 8 tests OK.
- spec-lint run 42656524799 (areas=delivery): "delivery - branch gate and trust rule" success; all other delivery jobs success; "docs check" failed (expected: M1 and W1, spec text is written at the join).

Branch head (code): 55dec4d08ce032e00ae76987da730e008a644e12 (this report commit follows it).

READY
