# DL304 report

Base: origin/main 2180dbb. gate.json and rust_ci.py (with `deny`) existed.

## What changed
- `delivery_common.py`: new optional step key `when_changed` (validated list of path patterns, matched like `widen_on`). `plan_step` skips the step with `no change under when_changed (...)` when no changed file matches. Steps without it are unchanged.
- Rust `gate.json`: the existing `deny` step moved after `lint` (steps and `fail_fast_order`) and got `when_changed`: `Cargo.toml`, `*/Cargo.toml`, `Cargo.lock`, `deny.toml`. Before, it ran on every change.
- `CONTRACT.md`: `when_changed` documented.
- Spec `features/delivery` (R5.x deny bullet) and change notes for `delivery`, `delivery-speed`, and `docs/architecture/changes/DL304-rust-gate-deny.md`.
- New `tests/test_dl304_rust_deny_step.py`.

## Tests
- `python3 -m unittest test_dl304_rust_deny_step test_ds200_rust_ci test_dl245_multi_track test_dl130_gate_fixes test_ds201_rust_workflows` (in delivery/tests): OK, 75 tests, 1 skipped.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only W1 on docs/work/ (expected).
- spec-lint.yml (areas=delivery), run 43447907751: failed only on docs check W1 (expected on a branch); T2 are warnings.
- template-build.yml, run 43447912729: success.

## Follow-ups
- A required step skipped for a `no ...` reason is accepted by gate_verify.py; `deny` is not a required step, so nothing to change.

Branch head: see `git rev-parse origin/DL304-rust-gate-deny`.

READY
