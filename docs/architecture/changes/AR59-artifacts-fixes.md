---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
Fixes from the plugin review. A deferred Full Progress publish no longer makes the Stop hook or the hourly helper ask for a publish. Queue writes are locked and use a per-process temp file, so no event is lost. A "DD Mon" date in --started or --phase takes the year nearest now. The after-command hook reads quotes and operators properly and trusts the exit code only when it belongs to the gh command. Session start no longer re-queues a merged status while a newer pull request is open. An Expected over six weeks in the past counts as a plan for the next occurrence, not as overdue, and 29 Feb now parses. repo_root decodes git output as UTF-8. Hook commands fall back to python without rerunning a script that blocked.
