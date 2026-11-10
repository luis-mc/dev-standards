---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: major
breaking: true
---
luismc-docs now holds the project record and artifacts (feature artifacts, Full Progress, task registry, hooks and five skills) and the spec-new and spec-check skills; luismc-artifacts and luismc-specs leave the marketplace (D182, D185, D186). Skill names change to luismc-docs:<skill>. The record defaults to docs/project when neither .claude/artifacts.json nor a docs.json record_dir exists.
