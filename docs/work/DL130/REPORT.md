# DL130 report

## Changes
- DL130 (pre-push): when `package.json` and `pnpm-lock.yaml` exist, `scripts/delivery/gate.json` has a `pnpm ` command and `node_modules` does not, the hook prints `pre-push: node_modules is missing in this worktree; run pnpm install --frozen-lockfile here.` and exits 1 (after the `scripts/delivery` check, before Python/guards).
- DL137 (pre-push): the stale path was `hooks_dir` from `$0`. `core.hooksPath` is shared by all worktrees, so a hook run from an older worktree used that worktree's `pre-push.local`. The hook now compares its own dir with `<git rev-parse --show-toplevel>/.githooks` and, if they differ and the current one has a `pre-push`, `exec`s it (guard variable `PRE_PUSH_REEXEC` stops a loop).
- DL131 (branch_gate.py): after the steps run, `docs/work` is restored (`git restore --staged --worktree`, `git clean -fd`, that folder only). The tree was clean at start, so only gate output is touched. The next push or gate run sees a clean tree.
- DL134: `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `FORCE_COLOR=0`, `NO_COLOR=1` are set in the gate's environment (children inherit). stdout/stderr reconfigured to UTF-8 with `errors=replace`. After the run each step log is rewritten as UTF-8: bytes decoded as UTF-8, else cp1252 with replace; ANSI sequences removed; CRLF to LF.
- DL141: if the branch changes `.cs`/`.csproj`, each owning project is built with `dotnet build` when dotnet exists and the project is not Windows-only (off Windows). Otherwise the result gets `"warnings": ["C# changed, not compiled on <os> (release CI compiles it)..."]` and the summary prints `warning : ...`. A failing build adds a failed step `csharp-build`. Skipped when `--only`/`--skip` is used.
- Note: `delivery_common.py` was not touched (not owned); all fixes sit in `branch_gate.py`.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl130_gate_fixes.py`: 9 tests OK (includes two-worktree hook test).
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_dl1*.py"`: 128 OK.
- `sh -n` on the hook: OK.
- `python3 tools/ci_areas.py --branch-advice`: see below.
- `docs_check.py`: M1 x3 (delivery, delivery-speed, project-setup specs need the spec text above; orchestrator writes it), T2 x2 warnings. No G1/W1 shown.

