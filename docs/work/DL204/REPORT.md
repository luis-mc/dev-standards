# DL204 report

Base check: `ci_rerun_first.py` held `by_key = {}` (line 113) on origin/main. OK.

## What changed
- `ci_rerun_first.py`: `by_key` renamed to `by_name`. A scan of all delivery templates and the installer script found no other secret-shaped assigned name (workflow files and the CI database DSN are skipped by the hook's own rules).
- `.gitleaks.toml` (delivery template): `[allowlist] paths` names exactly `.delivery/ci-install-base/` and `.delivery/ci-install-state.json`.
- project-setup `.githooks/pre-commit`: layer 1 skips the same two paths.
- `branch_gate.py`: new `ignore_untracked_work`; untracked files under `docs/work/` no longer make the tree dirty. A changed tracked file there still does. (Only `branch_gate.py` checks the clean tree; no pre-push template change was needed.)
- New `test_dl204_install_secret_scan.py`: guard over templates and installer script, over a temp install of every track (pattern read from the hook), allowlist paths, hook skip, and the docs/work cases.
- Docs: delivery spec R13.93; feature notes for delivery, delivery-speed and project-setup (docs_check M1 required the last two); two plugin change notes.

## Tests
- `python3 -B -m unittest discover` in delivery/tests: 1315 tests OK (1 skipped).
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/test_ci_areas.py`: all checks passed. `tools/test_project_setup_fixes.py`: 0 problems.
- `tools/test_delivery_gate.py`: ran its own mutant section, no FAIL line so far; stopped before the end because the brief forbids mutation passes. CI ran it (below).
- `docs_check.py`: only G1 (decisions.md stale, generated) and W1 (this report); both allowed.
- `gh workflow run spec-lint.yml --ref DL204-install-secret-scan -f areas=delivery` (run 43020346662): every delivery job success; "docs check" failed only on G1 and W1; the others skipped.

## Follow-ups
- `claude/plugins/docs/templates/design-system/components/react-typescript/number-keypad.css` line 41 (`.ds-keypad__key:active {`) matches the hook pattern. Not owned here; rename the class or mark the line.
- `claude/plugins/docs/scripts/project_artifacts.py` also uses a `by_key` name (not a shipped template).

Branch head: see `git rev-parse origin/DL204-install-secret-scan`.

READY
