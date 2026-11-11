---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL230: the ts CI templates (`ci.yml`, `nightly-full.yml`) run `playwright install --with-deps chromium` only on GitHub-hosted runners. Self-hosted pool runners run `playwright install chromium`, because they have no sudo (D226).
