plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch

The DL-76 check in the Stop hook caches its verdict per merge commit in `.delivery/state/dl76-checked.json` (not the ledger), skips runs that were skipped, and spends `gh` calls on at most 3 trains per turn end, newest first. A cached finding still blocks. Output and DL-76 meaning are unchanged.
