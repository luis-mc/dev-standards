# DS206 report: Rust path filters and linker order

## What changed
- `rust/.github/workflows/ci.yml`: pull_request uses a positive `paths:` list (crates/**, **/Cargo.toml, Cargo.lock, rust-toolchain.toml, rustfmt.toml, deny.toml, **/*.rs, scripts/delivery/rust_ci.py, tools.json, this workflow). Rust under apps/ matches. Push keeps `paths-ignore` (docs/**, **/*.md, apps/ios, apps/android, packages/**, pnpm-lock.yaml); `apps/**` is no longer ignored on push.
- `ts/.github/workflows/ci.yml`: pull_request and push `paths-ignore` gain the Rust-only paths (all of the list above except tools.json). GitHub skips a workflow only when every changed file is ignored, so a Rust-only change skips the JS suite and a mixed change runs both.
- `rust/scripts/delivery/gate.json`: `toolchain-isolated` is false.
- `rust_ci.py`: isolation default is false (only an explicit true hides compilers). Linker order on Linux/macOS: system cc/gcc/clang, then pinned Zig, else exit 1 with `linker cc not found. Fix: install a C compiler (sudo apt-get install -y build-essential pkg-config), or pin Zig ...`. The "zig is not pinned" warning is gone. LLVM for the Windows MSVC target is unchanged.
- Tests: ds200 (isolation default, cc beats Zig, Zig fallback), ds201 (PR filter, ts ignore list, filter rules over sample file sets).
- Notes: `docs/architecture/changes/DS206-rust-filters.md`, `docs/features/delivery/changes/DS206.md`.

## Design choice
No `changes` job: the repo checks fix the exact job `if` text and `needs` of the ts jobs, so a gating job would have needed many check edits. Native path filters meet the brief and no check needed a change.

## Known limits
- A push to main that changes only JS under apps/web (not ios/android/packages) still runs the Rust workflow, because `paths-ignore` cannot re-include Rust files under apps/. PRs are exact.
- A skipped workflow leaves a required check of that workflow pending; branch protection must not require the Rust jobs on JS-only PRs (same as DS201).
- The feature spec text of `features/delivery` was not edited (not in the owned files); the feature note is added.

## Tests
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_ds20*"`: 31 OK.
- `workflows_conform` and `every_track_ci_skips_docs_and_markdown_on_push` (called directly from tools/test_delivery_ci.py; the full suite is blocked locally by the session guard): both OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: W1 (docs/work, expected) and two T2 warnings.
- `gh workflow run spec-lint.yml --ref DS206-rust-filters -f areas=delivery`, run 42684214850: overall failure from `docs check` only (W1). Delivery jobs, all success: setup preflight, train cleanup, CI scripts and workflow templates, packaged-program smoke test, runner plan, plugin ledger/recorder/watcher/hooks, artifact pruning, branch gate and trust rule, change notes enforced and folded, area mapping, delivery scripts/CI templates/cleanup/prune/change notes. Other jobs skipped (other areas).
- Workflows were not run on a real Rust or JS project.

Branch head: see `git log -1` on origin/DS206-rust-filters.

READY
