# DL332 report

The CI asset now takes its Node version from the project.

## Files
- claude/plugins/project-setup/skills/claude-setup/assets/ci/dev-standards.yml: a step picks .nvmrc, .node-version, .tool-versions or package.json; setup-node uses `node-version-file`; with none, Node 24. Pinned action SHAs unchanged.
- claude/plugins/project-setup/tests/test_dl332_ci_node_version.py (new dir; no project-setup tests dir existed)
- docs/features/project-setup/spec.md: R5.23 and a test row
- docs/features/project-setup/changes/DL332.md (feature note, minor)
- docs/architecture/changes/DL332-ci-node-version.md (plugin note, patch)
- SKILL.md: no mention of Node 22, no change.

## Commands
- `python3 -m unittest claude/plugins/project-setup/tests/test_dl332_ci_node_version.py`: 4 tests OK
- YAML parse (placeholders filled): OK. actionlint: not installed, skipped.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only error is W1 (docs/work on branch), expected; strip before the join.

Branch head SHA: see `git rev-parse origin/DL332-ci-node-version`.

READY
