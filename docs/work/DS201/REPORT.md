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
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_ds20*"`: 27 OK (DS199, DS200, DS201).
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area"; ran area `delivery`.
- `gh workflow run spec-lint.yml --ref DS201-rust-workflows -f areas=delivery`:
  - Run 42665260428: failed. `CI scripts and workflow templates` failed (`every_track_ci_skips_docs_and_markdown_on_push`, `workflows_conform`: the shared checks need push `paths-ignore` with docs and md, and no `RUNNER_TEMP` in the workflow; `workflow_checker_detects_each_defect`).
  - Fixes: kept `paths-ignore` (JS-only paths added: `apps/**`, `packages/**`, `pnpm-lock.yaml`) instead of a `paths:` list; env goes through a pipe, not a file in `RUNNER_TEMP`; kept the step name `Boundary check (§3.2, §3.3)`.
  - Run 42665896280: the ledger suite failed on a machine-load check (CPU 60.7% > 60%), a flake unrelated to this change; the checker failure above remained.
  - Run 42666472254 (final): success for runner plan, branch gate and trust rule, train cleanup, artifact pruning, CI scripts and workflow templates, change notes enforced and folded, setup preflight, packaged-program smoke test, ledger/recorder/watcher/hooks, area mapping, and the summary job. Only `docs check` failed.
- `docs_check.py` local: W1 (docs/work, expected on a branch) and T2 warning (delivery-speed spec older than code). M1 passes.

## Deviations
- The brief asked for a `paths:` list; the repo's CI checks (tools, not mine) require `paths-ignore` on push, so the Rust ci.yml ignores JS-only paths. The Rust paths are never ignored. The reverse (Rust paths ignored by the JS workflow) needs a change to the ts workflow, which I do not own.
- Rust apps under `apps/` would be ignored by this filter.
- The workflows were not run on a Rust project.

Branch head: see `git log -1` on origin/DS201-rust-workflows.

READY
