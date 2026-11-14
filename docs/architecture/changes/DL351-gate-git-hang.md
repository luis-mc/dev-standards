---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner gate no longer hangs on the ci-wait marker: its git commands run non-interactively with a 20 s timeout, `slot N taken` is logged before the claim check, and the doctor warns when a runner account has no non-interactive git credential.
