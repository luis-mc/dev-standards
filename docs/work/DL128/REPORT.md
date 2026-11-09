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
- Not run: the gh workflow (no gh CLI auth here; see below).
