---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The TS e2e gate step skips the Chromium download when E2E_CHROMIUM_PATH names an existing executable, so cloud sandboxes with a preinstalled browser can run it. agent_setup.sh finds a Chromium under /opt/pw-browsers and sets that variable.
