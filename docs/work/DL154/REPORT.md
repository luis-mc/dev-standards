# DL154 report

## What changed
- `fast_guards.py`: the pre-push secret-scan step (any `run` starting with `gitleaks `) gets `--gitleaks-ignore-path` from `git show <head>:.gitleaksignore` in a temp file (empty file when the commit has none), and `--config` from `.gitleaks.toml` when the commit has one. gate.json `run` strings are unchanged. The pre-push hook is untouched.
- Spec R13.78, change notes (`docs/architecture/changes/DL154-prepush-ignore-file.md`, `docs/features/delivery/changes/DL154.md`), new test file.

## Did the bug reproduce?
Not with real gitleaks: it is not installed here. By reading the code: when the pushed commit is not HEAD, the temp worktree is the pushed commit, so its ignore file already came from the commit. The bug is real when the pushed commit is HEAD and the working tree differs (dirty or edited ignore file). Per D156 the fix is applied anyway; the command builder is tested without gitleaks (HEAD with dirty tree, not HEAD, no ignore file, config, other steps).

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl154_prepush_ignore.py`: OK, 5 passed, 1 skipped (real gitleaks).
- `python3 tools/test_delivery_gate.py --no-mutants -k secret`: 0 checks matched; nothing to fix. The full gate suite is left to CI (session guard).
- `docs_check.py` locally: G1 (decisions.md stale) also fails on main, not mine and generated. M1 is answered by `Docs: none` in the commit message.
- spec-lint run 42717059613 (areas=delivery): all delivery jobs success (setup preflight, artifact pruning, runner plan, train cleanup, ledger/recorder/watcher/hooks, change notes, packaged smoke, branch gate and trust rule, area mapping, CI scripts and templates, delivery scripts/templates/cleanup); other areas skipped. `docs check` failed on G1 only, the same stale decisions.md that fails on main.

Branch head SHA: see `git rev-parse origin/DL154-prepush-ignore-file`.

NOT READY
