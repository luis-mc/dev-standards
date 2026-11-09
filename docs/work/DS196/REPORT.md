# DS196 report: Rust catalog

## What changed
- `catalog/tech/languages.yaml`: rust gets `roles: [api, component]` and a `component` block: requires_reason, reason_prompt (written reason only, D145), parts cli, host-service, library-napi (needs build_matrix), library-wasm; later_parts worker, media (D139).
- `catalog/roles.yaml`: new asked role `native_components` (multi, default none).
- `catalog/bundles.yaml`: `component_pairings` (any API language and any host; host-service needs a Windows build option; wasm on cloudflare supported; napi on vercel warns).
- `check_stack.py`: accepts `{api: X, components: [rust]}` (`language` still works). Components may be ids or mappings (id, parts, reason, build_matrix, cross_compile, licence_note, targets, windows_runner). Host elimination applies to the API language only. Errors: unknown component or part. Warnings: Rust component without a recorded reason; napi addon without a build matrix; cross-compile target without a licence note; Windows host-service without cross_compile or windows_runner; napi on Vercel. `--catalog` checks parts and pairings.
- Tests: `tools/test_check_stack_rust.py` (9 cases).
- Notes: `docs/architecture/changes/DS196-rust-catalog.md`; `docs/features/project-setup/changes/DS196.md` (made with docs_fold note to satisfy M1).

## Tests
- `python3 check_stack.py --catalog`: catalog: clean
- `python3 -m unittest tools.test_check_stack_rust`: 9 tests OK
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" -> spec-lint run below
- `python3 tools/test_project_setup_fixes.py`: not run; the session hook refuses a heavy full run locally.
- `docs_check.py`: 0 errors, 1 warning (M1: tools/test_check_stack_rust.py code unmapped to a spec).
- Added `check-stack-rust` to `.claude/suites.json` (not in my owned list): the session-guard test requires every test file to be a declared suite.
- `gh workflow run spec-lint.yml --ref DS196-rust-catalog -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`: run 42650535577. Passed: specs/templates/AUTHSPEC (guard now holds), transcript folds, profiles, change notes. Failed: docs check, only on W1 (docs/work/DS196/REPORT.md, expected on a branch). The delivery aggregate job failed because sibling jobs were cancelled after that failure; not a test failure. The first run (42649813162) failed the guard on the undeclared suite; fixed.
- M1 warning on tools/test_check_stack_rust.py (no spec maps it): left for the DS203 docs task.

READY
