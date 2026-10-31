---
id: quality
title: Quality goals and constraints
type: explanation
owner: owner
last_verified: 2026-10-31
---
# Quality goals and constraints

## Quality goals

In priority order:

1. **Rules that bite.** A rule is a hook, a script or a test, not a note. Each rule line names the requirement that enforces it.
2. **Stable citations.** Requirement IDs and section numbers do not move. Projects, hooks and tests cite them.
3. **Safe by default.** Plugins write files in the working tree and report. Audits never change code.
4. **Cheap to run.** Delivery and test cost stay low: agents test only what they touch, and CI runs only the affected areas.
5. **Readable by a person.** Plain, short English. The owner reads status pages, not code.

## Constraints

- **Machine load.** Heavy work does not start while memory is above 85% or CPU above 60% (DL-77). Running work is never killed.
- **No git writes by plugins.** Plugins do not commit, push or merge. The project does that when it chooses.
- **IDs kept stable.** A rewrite changes layout and wording only. Requirement IDs, section numbers and `**Version:**` lines stay.
- **Change notes, not version edits.** A branch adds a note. Only the release fold writes versions.
- **No other project named.** Nothing in this repository names a product or repository other than dev-standards and its plugins.
- **Generated files.** Scripts write the index files; nobody edits them.
- **No ready PR from an agent.** Agents work on task branches and open drafts. Merges happen at green CI on a release.
- **One owner.** Private marketplace, one maintainer, so no review queue exists. CI is the reviewer.

## Risks

| Risk | What is done about it |
|---|---|
| A rule drifts from the hook that enforces it | Rule tags name the requirement; `test_rule_tags.py` checks them. |
| A spec edit breaks a citation | Spec lint checks numbering and references on every pull request. |
| Parallel branches conflict on versions | Branches add change notes; the release folds them. |
| Docs go stale | The docs check warns on old `last_verified` and on code newer than its doc. |
| A runner goes offline and a release stalls | The watcher reports it and repairs the runner, then reruns the CI. |
| Tests grow slower | `tools/ci_areas.py` limits a run to the areas a change touches. |
| Agent briefs or reports reach `main` | `docs_work.py guard` fails the ready pull request. |
