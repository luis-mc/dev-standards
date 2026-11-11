---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

`delivery_ci_install.py update` no longer overwrites a plugin-owned file the project changed. It records a hash of every file it writes in `.delivery/ci-install-state.json` and a copy of each template in `.delivery/ci-install-base/`. A changed file is merged with a line-based 3-way merge (D206). A clean merge is written. On a conflict the project file stays and `<file>.new` holds the merged text with conflict markers. A file with no stored base is kept with a plain `<file>.new`. The run ends with a count summary and exits 0. The doctor check `ci.scripts-current` warns and names each changed file or pending `.new`. The project should commit `.delivery/ci-install-base/`.
