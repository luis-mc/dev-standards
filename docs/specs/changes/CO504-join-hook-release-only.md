---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The DL-11 join hook decides release branches by the new `join_branch_re` (default `release/<n>`), `release_branches` globs and `-integration`, never by `train_branch_re` or `release_branch_re`, which projects widen to agent branches; an agent's own gate on `claude/*` is allowed again.
