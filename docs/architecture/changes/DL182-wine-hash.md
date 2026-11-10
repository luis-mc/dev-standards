---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner-pool image clears the shell's command hash (`hash -r`) before its Wine wrapper self-check, so the image build no longer fails when Wine is installed.
