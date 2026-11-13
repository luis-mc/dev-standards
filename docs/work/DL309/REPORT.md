# DL309 report

Hooks: `hook_pre_tool.py` and `hook_stop.py` never read the CODE DONE line (one message text only), so no change there.

Files:
- claude/plugins/delivery/templates/shared/scripts/delivery/agent_ci.py (default marker, docstring)
- claude/plugins/delivery/tests/test_dl309_ticked_code_done.py
- docs/features/delivery/spec.md (R5.14, ID kept)
- docs/features/delivery/changes/DL309.md
- docs/architecture/changes/DL309-ticked-code-done.md
- docs/work/DL309/REPORT.md

Tests (from claude/plugins/delivery/tests):
- `python3 -m unittest test_dl309_ticked_code_done test_dl226_agent_ci_path_ci_watch`: 10 tests OK
- `python3 -m unittest test_dl153_agent_ci_wave`: 6 tests OK

docs_check: G1 (generated decisions.md stale, not committed per rules); M1 on delivery-speed spec is covered by `Docs: none` in the commit message.

READY
