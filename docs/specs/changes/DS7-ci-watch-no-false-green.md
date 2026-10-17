---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The post-tool hook records a ci_watch result only on the train whose CI head matches the watched sha; a sha that matches no train (another repository's) is no longer attached to the first pushed train.
