---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

`delivery_ci_install.py update` no longer overwrites a plugin-owned file the project changed. It records a hash of every file it writes in `.delivery/ci-install-state.json`. A changed file is kept, the new template goes to `<file>.new`, and the run prints a diff command. The doctor check `ci.scripts-current` warns and names such files.
