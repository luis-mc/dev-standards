---
title: Move a project to luismc-docs 2
type: how-to
---
# Move a project to luismc-docs 2

`luismc-docs` 2 holds what three plugins did: the documentation standard, the project record and artifacts (was `luismc-artifacts`), and the spec skills (was `luismc-specs`). The two old plugins are gone from the marketplace. There is no shim. This guide is for a project that installs plugins from the marketplace.

You need Claude Code open in the project.

## Steps

1. Update the merged plugin, at every scope where it is installed:

   ```bash
   claude plugin update luismc-docs@dev-standards
   ```

2. Remove the two old plugins:

   ```bash
   claude plugin uninstall luismc-artifacts@dev-standards
   claude plugin uninstall luismc-specs@dev-standards
   ```

3. Run `/luismc-project-setup:claude-setup` again. It enables six plugins in `.claude/settings.json` and drops the keys of the two old ones.
4. Use the new skill names (table below). Edit any note, script or rule of your own that spells an old name.
5. Check the record: `python3 <luismc-docs>/scripts/project_artifacts.py check`, or run `/luismc-docs:project-artifact-check`.

## Skill names

| Old | New |
|---|---|
| `/luismc-artifacts:feature-artifact-new` | `/luismc-docs:feature-artifact-new` |
| `/luismc-artifacts:full-progress-artifact-new` | `/luismc-docs:full-progress-artifact-new` |
| `/luismc-artifacts:project-artifact-check` | `/luismc-docs:project-artifact-check` |
| `/luismc-artifacts:task-add` | `/luismc-docs:task-add` |
| `/luismc-artifacts:task-status-update` | `/luismc-docs:task-status-update` |
| `/luismc-specs:spec-new` | `/luismc-docs:spec-new` |
| `/luismc-specs:spec-check` | `/luismc-docs:spec-check` |

## What else changes

- The scripts are in the `luismc-docs` plugin now. A command that ran `luismc-artifacts/scripts/project_artifacts.py` from the plugin cache runs `luismc-docs/scripts/project_artifacts.py`. The spec checker is `luismc-docs/skills/spec-check/assets/spec_check.py`.
- The artifacts session hook is `scripts/artifacts/hook_session_start.py`. You do not call it.
- Where the record lives when nothing says: `docs/project`. A project with `.claude/artifacts.json` keeps what that file says. A project whose `.claude/artifacts.json` has no `record_dir` keeps `docs/artifacts`. A project with a `record_dir` in `docs/docs.json` and no `.claude/artifacts.json` uses that folder.
- `luismc-delivery` needs `luismc-docs` 2.0.0 or later. `delivery_doctor.py check plugins.compat` says so when it is older.
- A project CI file that checks specs with the old script path (`claude/plugins/specs/skills/spec-check/assets/spec_check.py`) uses `claude/plugins/docs/skills/spec-check/assets/spec_check.py`. The `claude-setup` CI template does this already.
