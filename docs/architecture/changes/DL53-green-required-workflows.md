---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/architecture/DELIVERYSPEC.md
change: patch
---
DL-03 fix: `watcher.ci_workflows`, when set, is the whole required set. With no list, a release waits only for workflows that run on every pull-request commit; a closed-only trigger or a `paths` filter is not waited on (list such a workflow in `watcher.ci_workflows` to require it). RELEASE-40 waited for them, so no release could turn green.
