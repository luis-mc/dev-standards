# DS208 report

## What changed
- `templates/rust/test/rust-binaries.global-setup.ts`: vitest globalSetup. Builds each crate in `RUST_TEST_CRATES` with `cargo build --locked -p`, sets `<CRATE>_BIN`, fails clearly when cargo is missing.
- `templates/ts/.github/workflows/ci.yml`: `verify` job installs the pinned Rust toolchain before the unit tests, only when `scripts/delivery/rust_ci.py` exists (Rust track on). DL147 rules and path filters unchanged.
- `docs/guides/rust-beside-js.md`: section "TS tests that run a Rust binary".
- `docs/features/delivery/spec.md`: R13.82. Change notes added. New test `test_ds208_global_setup.py`.

## Installer
No change needed. `delivery_ci_install.py` copies every file under `templates/rust/` (it walks the folder), so `test/rust-binaries.global-setup.ts` lands in the project at `test/`. A TS-only project does not get it; a mixed project installs the rust track too.

## Tests
- ds208 tests (unittest discover, 3 tests): OK. dl147 workflow needs tests (5): OK.
- `tools/test_delivery_ci.py`: the session guard refuses a full local run. I ran `workflows_conform`, `shared_workflows_take_their_runner_from_the_variable`, `workflow_checker_detects_each_defect` and `check_workflow('ts', ...)` directly: all pass, no expectation moved.
- `docs_check.py`: one error, `docs/architecture/decisions.md` stale. It is generated, it fails the same on a clean main, and I did not touch it.

## spec-lint run 42717055232 (areas=delivery)
All delivery jobs: success (ledger/recorder/hooks, pruning, setup preflight, branch gate, runner plan, packaged-program smoke, train cleanup, CI scripts and workflow templates, area mapping, change notes enforced, aggregate). Other areas: skipped.
`docs check`: failure, two errors only. G1 `decisions.md` generated file stale (same on main; not mine to edit). W1 this report under docs/work/ (by design; stripped before join).

Branch head (code commit): d4e845c3f63a3db0ee6e7c4cc71ca2e9858fb1d7

READY
