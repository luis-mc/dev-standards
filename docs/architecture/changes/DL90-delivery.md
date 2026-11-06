---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The delivery ledger is found from a git worktree: `find_root` skips a `.delivery/` folder with no `config.json` or `ledger.json` and resolves a worktree to its main checkout. New `delivery_ledger.py link --pr N` links a PR to its train by hand. The pre-tool, stop and session hooks use the same lookup.
