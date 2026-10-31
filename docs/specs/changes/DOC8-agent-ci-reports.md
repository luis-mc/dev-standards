---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
agent_ci.py reads the agent report from docs/work/reports/ (DOCSPEC R10.1) and still reads docs/work/agents/reports/ and docs/agents/reports/ while projects migrate; join.py's strip of docs/work/ then covers the reports.
