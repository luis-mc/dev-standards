---
plugin: claude/plugins/audits/.claude-plugin/plugin.json
change: patch
---

The audit skills now agree with the shipped specs. Erasure accepts tombstones, retained audit records and a grace period, and rejects `VACUUM` as an erasure method. Accessibility targets WCAG 2.2 AA. The read budget follows STACKSPEC §14. Framework-only findings (FedRAMP High, DoD IL6) apply only when the project declares the framework. Removed a stray line and a duplicate contrast check, and `compliance review` now belongs to compliance-audit only.
