---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
`ci_watch.py` runs the project commands listed in `.delivery/config.json` `ci_watch.post_run` after each watched run finishes (placeholders `{run_id}`, `{head}`, `{conclusion}`, `{workflow}`); a failing hook is logged and never changes the verdict, so a project keeps its machine-only extras in its own hook instead of a forked `ci_watch.py`.
