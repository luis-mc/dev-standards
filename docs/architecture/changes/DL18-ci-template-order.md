---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The CI templates of all four tracks run the secret scan, format, lint, typecheck and boundary checks before codegen drift and the tests; each `gate.json` gains `fail_fast_order` and runs its steps in that order.
