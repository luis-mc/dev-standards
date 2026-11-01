---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
Workflow templates pin every action to a full commit SHA with the tag in a comment. The gitleaks install (agent_setup.sh and the ci.yml secret scan) fails closed when tools.json has no SHA-256 pin, and prints the tools_pin.py command.
