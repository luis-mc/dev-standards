---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The doctor finds Windows runners from the service list as well as from folders. A runner folder it cannot read is reported as found, with its account from the service and the folder checks as "needs an administrator shell" (a warning). A new `workflows` check lists each `runs-on` label and fails when no online runner of the repository carries it, and warns about literal self-hosted labels and an unset `CI_RUNS_ON_WINDOWS`.
