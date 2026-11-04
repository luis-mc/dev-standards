# DL56 report: delivery shared script fixes

All eight findings reproduced on current main (each new test failed first) and are fixed. The tests are in `tools/test_delivery_shared_fixes.py`, declared as suite `delivery-shared-fixes` in `.claude/suites.json` and run by `spec-lint.yml`.

| Finding | Result | Evidence |
|---|---|---|
| F12 renames | fixed | `--no-renames` in `ci_scope` and `area_select`; test saw only the new path before |
| F13 quoted `gh pr create` | fixed | quote- and heredoc-aware splitter in `session_guard.py` |
| F14 removed `---` line | fixed | headers skipped only before the first `@@`; test saw line 7 as empty text before |
| F15 lock race | fixed | lock linked into place whole; an empty young lock counts as held; stale lock renamed away |
| F16 non-ASCII names | fixed | `-z` and UTF-8 decode; test saw `"docs/caf\303\251.md"` before |
| F17 `--measure=NAME` | fixed | the `=` form is read |
| F18 `--draft=true` | fixed | `--draft=true` and `--draft=1` accepted; `--draft=false` still refused |
| F19 `dirty_paths` | fixed | `status -z`, no strip; test saw `delivery/ledger.json` before |

## Tests run
- `tools/test_delivery_shared_fixes.py`: 9 cases, all passed.
- `tools/test_delivery_runner.py`: all passed.
- `tools/test_change_notes.py`: 136 checks passed.
- `tools/test_ci_speedups.py`: 24 passed.
- `tools/test_session_guard.py this_repo`: passed (the full suite is refused by the session guard locally; PR CI runs it).
- `tools/test_delivery_gate.py`: not completed locally (stopped; CI-only suite).

## Outside my files
`.claude/suites.json` and `.github/workflows/spec-lint.yml` got one entry each for the new test file (a test in `tools/` must be declared). Other agents may touch the same lines.

Docs: none for the feature spec; the change note is `docs/architecture/changes/DL56-delivery-shared-fixes.md`.

`tools/test_delivery_gate.py` is declared CI-only (measure=false) and ran over 10 minutes locally, so I stopped it. The PR CI runs it. It covers `dirty_paths` through branch_gate and join.

READY
