---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: minor
---
The PreToolUse hook enforces the light join (DL-11): it denies the branch gate (`check:branch`, `branch_gate.py`, `run_suite.py --full`) on a release/integration branch, and denies an Agent or RemoteTrigger join brief that names the gate (`--keep-going`, `--time-limit`, `--full`); `checks_off: ["DL-11"]` switches it off.
