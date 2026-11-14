# DL353 report (retry on current main)

Branch `DL353-marker-off-v2`, cut from `origin/main`. The first attempt's code and test were ported by hand.

## Files
- `claude/plugins/delivery/scripts/runner_load_gate.py`: `_fallback_on(mod, root)` uses `fallback_settings(CS.read_config(root))['enabled']`; a missing or unreadable config is off. `Marker.__init__` then sets `mod=None` and `skipped='fallback off (no ci.fallback in .delivery/config.json)'`. DL351 timeout code untouched.
- `claude/plugins/delivery/tests/test_dl353_marker_off.py` (5 tests)
- `docs/features/runner-pool/changes/DL353.md` (minor), `docs/features/delivery/changes/DL353.md` (patch, added so docs_check M1 passes; spec.md not edited)
- `docs/architecture/changes/DL353-marker-off-no-fallback.md` (plugin.json, patch)

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl353_marker_off test_dl351_gate_git_hang`: OK (17)
- `python3 -m unittest tools/test_delivery_runner.py`: 0 tests, OK
- `docs_check.py`: 0 errors before the report was added; the only error now is W1 (report under docs/work/, stripped at the join)

## Proposed requirement sentence (runner-pool spec)
The runner gate writes no ci-wait marker and runs no git when the project's `.delivery/config.json` has no enabled `ci.fallback` (a missing or unreadable config counts as off); it logs one line saying why (DL353, D301).

Head SHA of the code commit: fe829955f51ab5ac553e32be675545f06658e268 (the report commit follows it).

READY
