---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL121 folds five fixes from a project that uses the delivery plugin into the shared scripts, all opt-in or neutral by default: artifact_prune.py gains configurable artifact groups with protections and retries on transient GitHub errors; session_guard.py no longer blocks a gh pull request command aimed at another repository; ci_scope.py gains the no_test_reads and package_json valves; ci_watch.py can trim Docker's disk after the runs (ci.docker_trim); cleanup.py writes the delivery log only on request and judges joined branches against the default branch as it was before a merge commit.
