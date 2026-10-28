---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
A branch ending `-integration` is a train by default (as `hooklib.is_release_branch` already treated it), so its PR registers when it is opened; the watcher adopts the one open pull request of a train pushed by hand that has no PR number, so its CI is read and the DL-06 merge gate can pass.
