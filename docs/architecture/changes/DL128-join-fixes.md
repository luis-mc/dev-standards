---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The shared join script gets five fixes. DL128 stops a branch that is stacked on an older head of another branch in the same join and says to prefer its side. DL129 adds `--create` for an integration branch that is not on the remote, and prints the exact command otherwise. DL135 names an api-mock "unhandled API call" teardown error in the light check as a join-interaction failure. DL140 runs the design-system visuals rebuild, `docs_index.py build` and `docs_check.py --strict` before the ready pull request and lists specs with T2 findings. DL145 builds on a local integration branch that is ahead of the remote, refuses when local commits would be lost, and resolves conflicts under `docs/work/`.
