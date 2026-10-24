# CO427 report: Needs you vs Waiting for other work

Branch `claude/CO427-needs-you-vs-waiting`.

## What changed
- The only "Waiting or on hold" section is the At a glance group `waiting` (R5.34). It is now **Waiting for other work**; a Waiting or On hold task that waits on the owner moves into the **Needs you** group (`you`), after Needs you tasks and before Failed. Needs you count, the Needs you sentence (R5.7) and a feature's generated summary (R5.36) include them, so the glance count equals the section.
- The record had no clean owner-vs-work signal (no Blocked status; `expected_basis` and `detail` are free text), so one optional field was added: `waits_on` = `owner|work` on a Waiting or On hold task. Absent means `work` (old grouping). Set with `--waits-on owner|work` on `task-add` and `set-task-status` (`""` clears it); dropped when the task stops waiting; `check` refuses other values and the field on a non-waiting row. It is in the publish fingerprint (R9.6).
- Rows of both groups (and Needs you tasks) read the dependency first (`span.glance-dep`: `expected_basis`, else the release it rides, else the first sentence of `detail`, 80 chars), then the item, then Expected; `check` verifies it.
- Files: `scripts/render_artifacts.py`, `scripts/project_artifacts.py`, `templates/project-artifact.css`, `references/artifactspec.md`, `skills/task-status-update/SKILL.md`, tests in `tools/test_render_artifacts.py` and `tools/test_project_artifacts.py`.
- Version: change note `docs/specs/changes/CO427-needs-you-vs-waiting.md` (plugin minor, ARTIFACTSPEC minor). This repo forbids version edits off integration branches; the release folds it.

## Spec IDs
New R5.34a. Edited R5.7, R5.33 text via the Changes line, R5.34, R4.8, R9.6, the `task-add` / `set-task-status` usage rows. Numbering unchanged (spec_check: 0 errors, the one existing gap warning).

## Decision for the owner
The brief says the two sections come "after the running work". Needs you stays first in the At a glance block (R5.7 keeps it always present and first, and it is the group an owner reads first); Waiting for other work keeps its old slot after Built. Reordering is a one-line change to `GLANCE_GROUPS` plus the order sentence in R5.34 if wanted.

## Tests run
- `run_suite.py render-artifacts` (full, 138 passed, 0 failed), including four new cases: `glance_splits_owner_waits_from_work_waits`, `glance_default_waits_on_work_keeps_old_grouping`, `glance_needs_you_count_matches_the_section`, `check_finds_a_wrong_split_or_dependency`.
- `run_suite.py project-artifacts` named cases only (the suite is heavy, declared not to run in full locally): the two new cases `test_waits_on_is_stored_and_defaults_to_work`, `test_check_refuses_a_bad_waits_on` plus 36 neighbouring status, check, publish and pending cases, all passed. The full project-artifacts and hooks suites are left to CI.
- `spec_check.py` on ARTIFACTSPEC: clean; `change_notes.py check`: ok.
- No test weakened; the only existing-test edits are none (new expectations live in new cases).
