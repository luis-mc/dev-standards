---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Windows runner setup: a runner already in the folder is removed with a remove token (GitHub refuses a registration token), its exit code is checked, and the removal runs before the folder is locked to the new account, so a failure leaves the old runner working (DL315).
