---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
The shipped gate.json of every track orders the steps guards, typecheck, lint, then tests and runs typecheck and lint in the pre-push hook; delivery_common.py rejects a gate.json that puts a test step before a required step (`required_steps`, default typecheck and lint) and never skips a required step for the time limit; gate_verify.py refuses a result where a required step is missing or skipped; the agents rule gains the gate order.
