---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL120: the delivery installer reads a project-owned `scripts/delivery/ci-install.json` with `keep` and `skip` lists. `update` never overwrites a kept file and reports it; `install` and `update` never write a skipped file.
