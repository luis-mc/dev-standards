# DS287-c report

Contract: R5.92 in `docs/features/delivery/spec.md`.

## Files
- `claude/plugins/delivery/templates/shared/scripts/delivery/rerun_tests.py`: `then` key (step 2), `go_affected`, `affected_invocations`, `--go-deps`, `--go-mod`, `jest` runner. `rerun_args.py` not touched.
- `claude/plugins/delivery/tests/test_ds287_rerun_affected.py`: new, 13 tests.

## Behaviour
- `--json` keeps every old key and value. It adds `then` (a list of invocations, `[]` when none). Text output adds `then=` lines.
- go: changed .go files map to import paths via the go.mod module path plus the directory. Step 2 is one invocation listing the changed packages and every package whose deps hold one. Deps come from `--go-deps FILE`, else `go list -deps` if go is on PATH (run only after a narrow answer), else `then` is `[]`.
- vitest: `related FILES --run`. jest (`--runner jest`, new): `--findRelatedTests FILES`. Only changed JS/TS files that are not docs.
- Other runners: `then` is `[]`. Valves, `rerun: whole`, green and non-failure runs: whole/current, `then` is `[]`.

## Tests run (all OK)
- test_ds287_rerun_affected.py: 13 tests
- test_dl375_rerun_narrowing.py: 33 tests
- test_dl410_rerun_cypress.py: 7 tests
- Check that a test can fail: making every go package "affected" failed 5 of the new tests.

## Not met / notes
- The workflow templates must run step 2 only after step 1 passes. That is the other agents' work, not done here.
- Step 1 for go/pytest still includes test files of changed code, as today.
- `go list` is not run in tests (no go use in CI here); only the fixture deps path is tested.
