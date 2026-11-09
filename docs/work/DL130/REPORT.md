# DL130 report

## Changes
- DL130 (pre-push): when `package.json` and `pnpm-lock.yaml` exist, `scripts/delivery/gate.json` has a `pnpm ` command and `node_modules` does not, the hook prints `pre-push: node_modules is missing in this worktree; run pnpm install --frozen-lockfile here.` and exits 1 (after the `scripts/delivery` check, before Python/guards).
- DL137 (pre-push): the stale path was `hooks_dir` from `$0`. `core.hooksPath` is shared by all worktrees, so a hook run from an older worktree used that worktree's `pre-push.local`. The hook now compares its own dir with `<git rev-parse --show-toplevel>/.githooks` and, if they differ and the current one has a `pre-push`, `exec`s it (guard variable `PRE_PUSH_REEXEC` stops a loop).
- DL131 (branch_gate.py): after the steps run, `docs/work` is restored (`git restore --staged --worktree`, `git clean -fd`, that folder only). The tree was clean at start, so only gate output is touched. The next push or gate run sees a clean tree.
- DL134: `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `FORCE_COLOR=0`, `NO_COLOR=1` are set in the gate's environment (children inherit). stdout/stderr reconfigured to UTF-8 with `errors=replace`. After the run each step log is rewritten as UTF-8: bytes decoded as UTF-8, else cp1252 with replace; ANSI sequences removed; CRLF to LF.
- DL141: if the branch changes `.cs`/`.csproj`, each owning project is built with `dotnet build` when dotnet exists and the project is not Windows-only (off Windows). Otherwise the result gets (only then) `"warnings": ["C# changed, not compiled on <os> (release CI compiles it)..."]` and the summary prints `warning : ...`. A failing build adds a failed step `csharp-build`. Skipped when `--only`/`--skip` is used.
- Note: `delivery_common.py` was not touched (not owned); all fixes sit in `branch_gate.py`.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl130_gate_fixes.py`: 9 tests OK (includes two-worktree hook test).
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_dl1*.py"`: 128 OK.
- `sh -n` on the hook: OK.
- `python3 tools/ci_areas.py --branch-advice`: heavy: delivery only (project-setup not named).
- Named delivery-gate cases locally (`tools/test_delivery_gate.py --no-mutants -k <case>`): freeze, scopes, logs, dirty, hook, publish, e2e_agent, only_skip, fast_guards, push_check and the rest: 0 failed. Two earlier CI failures were mine and are fixed: the node_modules check fired in test repos (now only when gate.json has a `pnpm ` command), and a new `warnings` key broke the exact result-key test (now written only when non-empty).
- `gh workflow run spec-lint.yml --ref DL130-gate-fixes -f areas=delivery`, run 42658976304 on 948b521: every delivery job passed (branch gate and trust rule included). Only `docs check` failed: M1 for the three feature specs, which wait for the orchestrator's spec text.
- `docs_check.py`: M1 x3 (delivery, delivery-speed, project-setup specs need the spec text above; orchestrator writes it), T2 x2 warnings. No G1/W1 shown.


## Spec text for the orchestrator
- project-setup spec: pre-push stops with the node_modules message when package.json, pnpm-lock.yaml and a gate.json `pnpm ` command exist and node_modules is absent; pre-push hands over to the pushing worktree's own `.githooks/pre-push` when core.hooksPath names another worktree's copy.
- delivery spec: gate restores docs/work after the run; UTF-8 logs and env; C# warning text `C# changed, not compiled on <os> (release CI compiles it)`, `warnings` in gate-result.json only when present, `csharp-build` failure step.

Branch head: see `git rev-parse origin/DL130-gate-fixes` (code head 948b521, plus this report commit).

READY
