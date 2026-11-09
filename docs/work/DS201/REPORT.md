# DS201 report: Rust workflows

## What changed
- `rust/.github/workflows/ci.yml`: `rust_ci.py toolchain` replaces dtolnay (both jobs); `rust_ci.py env` writes the linker env to `$GITHUB_ENV`; `Swatinem/rust-cache` only when `runner.environment == 'github-hosted'`; pinned cargo-deny put on PATH with `ci_tool.py tool cargo-deny --dir` and run as `rust_ci.py deny` (one step covers bans and advisories); `paths:` list for Rust files, scripts and tools.json replaces `paths-ignore`; `cancel-in-progress` unchanged and equal to the ts workflow's; `|| true` removed from the sqlx-cli install.
- `rust/.github/workflows/package.yml`: same setup; new Windows exe build (cargo-xwin) and artifact `packaged-program-windows` beside `packaged-program`; no download from other runs; `tools.json` added to the paths.
- `delivery_common.py`: new `scope_skip`, called first in `plan_step`. A step with `paths: KEY` is skipped when files changed, all lie under some `scope_map` key, and none under KEY. Unmapped files, unknown keys, no `scope_map`: unchanged.
- Tests: `tests/test_ds201_rust_workflows.py` (12). Notes: architecture, features/delivery, features/delivery-speed.

## Notes
- A Rust-only change selects the Rust steps; JS steps are skipped only if they carry `paths: "js"` and the gate.json has a `js` scope_map key. The shipped Rust gate.json has only `rust`.
- The workflows were not run for real (no Rust project here).

## Tests
