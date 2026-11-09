# DS200 report: rust_ci helper

## What changed
- New `templates/rust/scripts/delivery/rust_ci.py` (stdlib only, uses `ci_tool.py` in process). Subcommands:
  - `toolchain`: installs the exact channel from `rust-toolchain.toml` (and its targets) with the pinned `rustup-init`. A non-exact channel such as `stable` fails.
  - `env [--format json|sh|cmd]`: linker env. Windows MSVC target: pinned LLVM `lld-link`, `clang-cl`, `llvm-lib`. Linux host: pinned Zig through a wrapper when pinned, else system `cc`/`gcc`/`clang` (with a warning that Zig is optional and not pinned), else fails `linker cc not found. Fix: ...`.
  - `deny`: advisory DB in `<tool cache>/advisory-db`, generated `deny.generated.toml` with `db-path` (committed `deny.toml` untouched), `cargo deny fetch` then `check --disable-fetch`. Fetch failure: cache up to 7 days old warns (stderr and `$GITHUB_STEP_SUMMARY`), older fails, none fails (D142).
  - `run [--] CMD...`: runs with the linker env; when gate.json `toolchain-isolated` is not false, folders holding cc/gcc/clang/ld are removed from PATH (folders holding cargo/rustc are kept; linkers are set by absolute path).
  - `smoke`: for each name in smoke.json `smoke.binaries`, debug build then `<bin> --version`.
- `gate.json`: `toolchain-isolated: true`, new `deny` and `xwin` steps, `scope_map` (Rust paths) and `paths: "rust"` on Rust steps; cargo steps run through `rust_ci.py run --`. `widen_on` still has `Cargo.lock`.
- `smoke.json`: `binaries: []` added.
- Tests: `tests/test_ds200_rust_ci.py` (15, fake cargo, fake tools, no install).
- Notes: `docs/architecture/changes/DS200-rust-ci-helper.md`, `docs/features/delivery/changes/DS200.md`.

## Gaps and follow-ups
- Zig is not pinned; treated as optional, the message says so.
- `scope_map` and step `paths` are written in gate.json but `delivery_common.py` (not mine) does not read them yet; the loader ignores unknown keys and all step scopes stay valid. A later task must make step selection use them.
- `toolchain-isolated` is read by `rust_ci.py`, not by the loader.
- `deny` passes `--config` before the subcommand (needs a cargo-deny with global `--config`; the pinned 0.20.2 has it, not run for real).
- delivery_doctor.py on my base has no Rust code, so I did not edit it. Strings to change on DS202's branch (current -> real):
  - `_cc_fix`: `python scripts/delivery/ci_tool.py ensure zig` (twice) -> Zig is not pinned; use `python3 scripts/delivery/tools_pin.py entry zig ...` then `python3 scripts/delivery/ci_tool.py tool zig`; message should say Zig is optional.
  - `rust.windows`: `python scripts/delivery/ci_tool.py ensure llvm` -> `python3 scripts/delivery/ci_tool.py tool llvm --exe lld-link`.
  - `rust.pins`/`rust.advisory`: `rust_ci.py deny` is correct as is.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_ds200_rust_ci test_ds199_tool_fetch test_dl115_ci_tool test_dl116_fetch_check`: 52 tests OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area"; ran the delivery smoke above.
- `docs_check.py`: 1 error (W1 docs/work, expected), 1 warning (T2 delivery-speed). M1 passes.
- `gh workflow run spec-lint.yml --ref DS200-rust-ci-helper -f areas=delivery`: run 42656168372, conclusion **failure**. All delivery suites passed (CI scripts, packaged-program smoke, branch gate, ledger/watcher, change notes, area mapping, setup preflight, train cleanup, prune, scripts job). Only `docs check` failed: M1 on `docs/features/delivery-speed/spec.md` (code inherited from DS199, `ci_tool.py` and `tools.json`, maps to that spec; no note exists for it, and it is not a file I own) and W1 (docs/work, expected). Fix: a `delivery-speed` change note (or `Docs: none`) on DS199 or at the release fold.

## Verdict
Code and tests are done and the delivery suites are green. The docs check is red from the inherited delivery-speed M1, so this branch is not ready until that note exists.

Branch head: the commit before this report update; see `git log -1` on origin/DS200-rust-ci-helper.

NOT READY
