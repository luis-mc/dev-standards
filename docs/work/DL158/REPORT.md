# DL158 report

## What changed
- `hook_pre_tool.py`: `overlaps` now compares paths segment by segment (`**`, fnmatch both ways, plain directory owns its subtree). Trailing `(note)` is cut and shown in the DL-41 message. Prose entries are ignored. `owns:` splits on commas outside parentheses. Same file with disjoint requirement IDs and `only` notes is allowed.
- New tests: `claude/plugins/delivery/tests/test_dl158_owns_overlap.py`.
- Spec R13.83, change note, feature note.

## Tests
- `python3 claude/plugins/delivery/tests/test_dl158_owns_overlap.py`: 8 passed.
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p test_pre_tool.py`: 31 passed.
- `python3 tools/test_delivery_hooks.py dl41_owns_overlap`: 55 passed, 0 failed (the full suite is heavy, left to CI).
- `python3 claude/plugins/docs/scripts/docs_check.py`: one error, G1 `docs/architecture/decisions.md` generated file stale. It fails the same way on main; not mine, generated file not committed.
- No .claude/suites.json line added: the new file is under the plugin tests folder, not tools/.

## CI
(spec-lint result below)

