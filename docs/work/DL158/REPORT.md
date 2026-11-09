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
Run 42717573648 (spec-lint.yml, areas=delivery): overall failure, from one job.
- docs check: failure. G1 `docs/architecture/decisions.md` generated file stale (also fails on main). W1 `docs/work/DL158/REPORT.md` added on the branch (expected; stripped before the join).
- success: which areas, CI scripts and workflow templates, packaged-program smoke test, train cleanup, setup preflight, runner plan, artifact pruning, branch gate and trust rule, change notes enforced and folded, plugin ledger/recorder/watcher/hooks, area mapping, delivery scripts/CI templates/cleanup/prune/change notes.
- skipped: change notes, change notes folded, artifact renderer, model profiles, branch gate shard, docs plugin, transcript folds plugin, specs/templates/AUTHSPEC.

Branch head SHA: see `git rev-parse` on the pushed branch (code commit 297733e; report commit follows).

READY

