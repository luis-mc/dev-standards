---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The PostToolUse recorder splits command lines with a real tokenizer (quotes, heredocs, redirections), records a backgrounded push or PR as bash.backgrounded instead of as done, retries a busy ledger lock once and logs a lost record to blocks.log; the watcher adopts the PR of a planned or joined train and re-points a moved head, `plan` adopts an open PR at once, and runner.guard_started is logged once.
