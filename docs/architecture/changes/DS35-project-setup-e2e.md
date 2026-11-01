---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
The delivery tooling records the e2e run in gate-result.json, adds branch_gate.py --e2e-only and e2e_push_check.py, and gate_verify.py and agent_ci.py refuse a UI branch without a passing e2e record.
