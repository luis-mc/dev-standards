---
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
The join runs a quick check (install, build, typecheck and the tests of the joined branches' affected packages plus their dependents) instead of a second full gate, and records each step's time; the pre-push hook freezes a branch while its ready PR's CI runs (override with DELIVERY_FREEZE_OVERRIDE=1; offline it allows the push with a warning); join.py and ci_watch.py warn when no online runner carries a label CI needs, and the runner question in tech-stack-setup warns against a label only one runner carries.
