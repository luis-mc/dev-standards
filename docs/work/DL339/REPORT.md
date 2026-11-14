# DL339 report

Branch: DL339-hook-python

## Files
- claude/plugins/delivery/scripts/delivery_runner_pool.py: `is_user_profile_path`, `choose_hook_python`, `Probe.python_config`; used by the runner-hooks step, the files/service steps (via the step problem) and the host-load task.
- claude/plugins/delivery/scripts/delivery_doctor.py: `hook_python_items` (`machine.hookpython:<file>`).
- claude/plugins/delivery/tests/test_dl339_hook_python.py (new).
- docs/features/runner-pool/spec.md (R5.46, R5.47, test row), docs/features/runner-pool/changes/DL339.md, docs/architecture/changes/DL339-hook-python.md.

## Notes
- The gathered host `python` is now only the machine-config value (`python` in machine.json or DELIVERY_HOOK_PYTHON), so "explicit wins" is real; sys.executable is used only outside a user profile.
- test_dl310_windows_runner.py needed no change.

## Tests (python3 -m unittest, from claude/plugins/delivery/tests)
- test_dl339_hook_python: 8 OK
- test_dl310_windows_runner: 42 OK
- test_dl316_windows_only_generic: 16 OK
- test_dl318_doctor_locked_runner: 8 OK
- docs_check.py: 0 errors, 0 warnings

Branch head SHA: see `git rev-parse origin/DL339-hook-python`.

READY
