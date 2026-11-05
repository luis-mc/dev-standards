---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---

CI now runs the TypeScript design-system guard templates. A new driver, `tools/test_ds_guard_templates.py`, builds fixture projects with `design_system.py`, installs vitest 3.2.4 in a temp folder and runs the four template files. It checks a clean project, a project with v1 archived and v2 live, and a project with a real version gap. No template needed a fix.
