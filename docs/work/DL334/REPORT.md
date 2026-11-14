# DL334 report

Branch: DL334-pr-exception (ships in RELEASE-134).

## Files
- docs/architecture/DELIVERYSPEC.md: DL-73 table row and section-3 row reworded, ID kept.
- claude-setup assets: rules/agents-and-integration.md (DL-73 line, tag kept), settings.json (permissions.allow with gh pr create, ready, edit), SKILL.md (settings step row, why in one line).
- tools/test_delivery_hooks.py: case dl334_pr_open_ready_edit_not_denied. hooklib.py untouched.
- claude/plugins/project-setup/tests/test_dl334_pr_allow_rules.py (new).
- docs/features/project-setup/spec.md: R5.23 and test row; changes/DL334.md.
- docs/architecture/changes/DL334-pr-exception.md: plugin project-setup (minor) and DELIVERYSPEC (minor).

## Tests
- `python3 claude/plugins/project-setup/tests/test_dl334_pr_allow_rules.py`: 3 ok.
- Named cases dl334_pr_open_ready_edit_not_denied and dl73_outbound_send_from_config, run by import (the full delivery-hooks suite is guarded, left to CI): both ok.
- `python3 claude/plugins/docs/scripts/docs_check.py`: G1 (generated docs-map stale, not committed by rule) and M1 for delivery, delivery-speed, models specs; those commits say `Docs: none` for those specs. The project-setup spec is covered by its note.
- Branch head before this line: 1811f0fc4be39fb1053a9c12c43355f02001beab (pushed). The docs_check M1 errors clear via the commit message line.

READY
