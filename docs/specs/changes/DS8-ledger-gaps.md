---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
luismc-delivery 0.3.2: the post-tool hook creates the train for a `gh pr create` of a release branch that has none (also with `--repo`/`--body-file`), sets its pr, state `ci` and `ci.head_sha`; a `git push` of a release branch that already has a PR sets `ci.head_sha` to the pushed head, resets `ci.state` to queued and clears `green_at`; `cd <dir> && ...` and `git -C <dir>` resolve the branch in that directory.
