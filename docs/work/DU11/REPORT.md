# DU11 report

## Bugs and fixes
- K1: `hook_design_edit.py` respond() first breach no longer returns `permissionDecision`; it passes `additionalContext` only. A repeat is still denied.
- K2: decide()/scan_added() count matches in old and new text and report only an increase. Old text: Edit old_string, MultiEdit each old_string, Write the file on disk (empty if absent). New stylesheet (Write) is a breach; an Edit to an existing stylesheet is not. Test files (*.test.*, *.spec.*, `__tests__`, `tests`) are skipped.
- K3: `plan_rows_check.py` find_rows() counts a row only under a heading starting Plan, Proposed, Proposals or Findings; any other heading ends the section; "Not proposed" never counts. Docstrings, Stop hook text and task-add SKILL.md updated.

## New tests (tools/test_ds_enforcement.py)
- hook_first_breach_has_no_permission_decision_and_repeat_is_denied
- hook_judges_what_an_edit_adds_not_the_whole_text
- plan_rows_count_only_under_plan_like_headings
Existing tests changed to expect no permissionDecision on the first breach.

## Docs
Change notes: DU11-delivery.md, DU11-artifacts.md, features/artifacts/changes/DU11.md.

## Commands
- python3 -I tools/test_ds_enforcement.py: 33 passed, 0 failed
- (pending) test_delivery_hooks.py, test_project_artifacts_hooks.py
- docs_check.py: 1 error G1 (generated docs/architecture/decisions.md is stale; the release fold regenerates it; not committed per rules), 3 T2 warnings.
- ci_areas.py --branch-advice: diff unreadable, advises every area via a CI workflow (heavy); not run.

NOT READY
