# DL146 report: mock handler guard

## What changed
- `claude/plugins/delivery/templates/ts/scripts/delivery/mock_handler_guard.py`: new guard. Reads the branch diff (`--base-ref`, default origin/main), finds new exported functions in API client files, and fails when the route has no default handler in the shared e2e mock. Paths come from `e2e_mock` in `.delivery/config.json`, with ts defaults. No files found: pass with a note.
- `claude/plugins/delivery/tests/test_dl146_mock_handler_guard.py`: 5 tests.
- `docs/features/delivery/spec.md`: R13.81 added after R13.71 (end of section 13), limits stated.
- Change notes: `docs/architecture/changes/DL146-mock-handler-guard.md`, `docs/features/delivery/changes/DL146.md`.

## gate.json entry for the release join (ts template, add to "steps", fast guard, after "guards")
```json
{
  "name": "mock-handler-guard",
  "scope": "always",
  "pre_push": true,
  "run": "python3 scripts/delivery/mock_handler_guard.py --base-ref {base} || python scripts/delivery/mock_handler_guard.py --base-ref {base}"
}
```
Also add `"mock-handler-guard"` to `fail_fast_order` after `"guards"`.

## Tests
- `python3 claude/plugins/delivery/tests/test_dl146_mock_handler_guard.py`: 5 tests, OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, `G1 docs/architecture/decisions.md: generated file is stale`. Generated file, not mine to commit; not caused by this branch.
- `python3 tools/ci_areas.py --branch-advice`: unreadable diff, run all areas.
- suites.json: not changed; the test sits in the plugin tests folder, not tools/.
STATUS_PLACEHOLDER
