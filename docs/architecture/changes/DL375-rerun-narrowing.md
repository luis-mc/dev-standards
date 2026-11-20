---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Adds rerun_tests.py: after a red run, a test job reruns the failed tests plus the tests of changed code, and the whole job on a valve change, a cancelled or timed-out run or an unreadable failure list (ci.jobs.<job-id>.rerun).
