---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The shipped scripts no longer name a variable so that it trips the secret scan, and the shipped .gitleaks.toml skips the installer's own state files. The branch gate ignores untracked files under docs/work/.
