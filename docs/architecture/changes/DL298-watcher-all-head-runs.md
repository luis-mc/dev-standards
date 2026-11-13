---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

# DL298 watcher counts every run on the head

The watcher lists every workflow run of the PR head. A workflow with a `pull_request` run on the head joins the configured list as required, so a failing path-filtered workflow blocks the merge. Runs made before the PR was ready are ignored, and a draft PR is never green. New key `watcher.ignore_workflows` excludes a workflow that is not a CI gate. Owner decision D264.
