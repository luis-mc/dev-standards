# AR67 report

## What changed
- AR67: `pending --refresh` renders first (new `render_changed` helper, shared with `render`), so the publish copy matches a fresh render and `mark-published` accepts it. The refusal text now names `render` or `pending --json --refresh`.
- AR68: task-status-update skill lists `--phase NAME=HH:MM-HH:MM` with names agents, join, ci, merge.
- New tests: tools/test_artifacts_ar67.py. Change note and feature note added.

## Tests
- `python3 -I tools/test_artifacts_ar67.py`: 3 passed, 0 failed
- `python3 -I tools/test_artifacts_ar63.py`: 7 passed, 0 failed
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff", advises spec-lint on every area.
- `python3 -I tools/test_project_artifacts.py`: started, did not finish within 150 s, twice; no result.
- spec-lint (areas=artifacts) dispatched through the GitHub tool: run 42655022825 on head f2c9e95, still in progress after about 10 minutes. Result not recorded. https://github.com/luis-mc/dev-standards/actions/runs/42655022825
- `docs_check.py`: W1 error (expected on a branch: this report); warnings M1 (tools/test_artifacts_ar67.py is not mapped by a spec `code:`; the spec is not mine to edit) and T2 (spec older than code; the release fold handles it).

## Head SHA
f2c9e95a5201b5a7d0de2b0f6adc15b25246832b (code); the report commit follows it.

NOT READY
