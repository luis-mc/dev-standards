# AR74 report: phase dates

Fix: an HH:MM-only phase list takes the occurrence of its first time nearest now; chaining follows (R5.44a). A phase over 12 h ahead of a past one warns. `--phase ""` with phases is still refused, now with the two-call hint. A Waiting release with --expected over old phases names the fix.

## Files
- claude/plugins/docs/scripts/project_artifacts.py (parse_phases, apply_release_fields hint)
- claude/plugins/docs/references/artifactspec.md (R5.44a)
- docs/features/artifacts/spec.md (R5.22, test row), docs/features/artifacts/changes/AR74.md
- docs/architecture/changes/AR74-phase-dates.md
- claude/plugins/docs/tests/test_ar74_phase_dates.py

## Tests
- python3 claude/plugins/docs/tests/test_ar74_phase_dates.py: 8 OK
- test_dl359_phase_gap_midnight.py: 3 OK; test_dl305_fix_phase.py: 6 OK
- python3 tools/test_project_artifacts.py release_flags release_expected release_refusals phase_crossing_midnight: 5 passed
- docs_check.py: only W1 (docs/work report on the branch, expected for agent branches); change_notes check: ok

Branch head (before this report commit): 2637414

READY
