# AR67 report

## What changed
- AR67: `pending --refresh` renders first (new `render_changed` helper, shared with `render`), so the publish copy matches a fresh render and `mark-published` accepts it. The refusal text now names `render` or `pending --json --refresh`.
- AR68: task-status-update skill lists `--phase NAME=HH:MM-HH:MM` with names agents, join, ci, merge.
- New tests: tools/test_artifacts_ar67.py. Change note and feature note added.

## Tests
- `python3 -I tools/test_artifacts_ar67.py`: 3 passed, 0 failed
- `python3 -I tools/test_artifacts_ar63.py`: 7 passed, 0 failed
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff", advises spec-lint on every area.
- `python3 -I tools/test_project_artifacts.py`: started, did not finish within the 2-minute smoke window (see below).
- `gh workflow run spec-lint.yml`: NOT run; `gh` and workflow dispatch are not available in this session.
- `docs_check.py`: 0 errors, 1 warning: M1 for tools/test_artifacts_ar67.py (no spec maps it; the spec is not mine to edit). G1/W1 not shown.

## Head SHA
See the branch head on origin.

NOT READY
