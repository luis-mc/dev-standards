# DL228 report

Base check: `the change would make the record invalid` was present in project_artifacts.py at checkout.

## What changed
- `with_details()` in project_artifacts.py adds the validator's errors to the message of every invalid-record failure (the generic one, content/<key> invalid in render and retire, edit-content). The errors name the entry id and rule, for example a decision with fewer than 2 options.
- `task-add` now checks `--item` first: `item is 93 characters; the limit is 80`. `set-task-status` uses the same text.
- `edit-content` of a decisions file prints `run docs_index.py build: docs/architecture/decisions.md is now stale`. The plugin has no pattern for rebuilding generated files, so no rebuild. `add_notes` now keeps notes already in the result.
- Spec: failure-mode rows in docs/features/artifacts/spec.md; feature note DL228; change note DL228-record-messages.md (patch, docs plugin).

## Tests
- `python3 claude/plugins/docs/tests/test_dl228_record_messages.py`: 4 tests OK (long item, with_details message, invalid decision names D1 and options, edit-content build line).
- `python3 -m unittest discover` in claude/plugins/docs/tests: 204 tests OK.
- tools/test_project_artifacts.py not run (heavy suite, hook refuses it locally); left to CI.
- `gh workflow run spec-lint.yml --ref DL228-record-messages -f areas=docs`, run 43064413953, all jobs ended: docs plugin success; which areas success; docs check failure (only G1 decisions.md stale and W1 docs/work, both expected); all other jobs skipped.
- docs_check.py locally: same G1 and W1 only, plus M1 for features/docs, answered by `Docs: none` in the commit message.

## Follow-ups
- Run docs_index.py build at release; do not commit generated files.
- Strip docs/work before the join.

READY
