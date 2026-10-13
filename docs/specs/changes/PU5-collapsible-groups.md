---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
Every checklist group in Full Progress and in feature artifacts is a collapsible native `<details>` (R6.12): the heading sits in the `<summary>`, `Live or built` always starts closed (and says how many Built and Live rows it holds), every other group starts open, and the `Earlier` fold now sits inside `Live or built`.
