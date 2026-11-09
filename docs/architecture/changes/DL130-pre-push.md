---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
The pre-push template now stops a push from a worktree that has `package.json` and `pnpm-lock.yaml` but no `node_modules`, and says to run `pnpm install --frozen-lockfile` there (DL130). It also resolves every path from `git rev-parse --show-toplevel` of the pushing worktree: when `core.hooksPath` names the hooks of an older worktree, that copy hands over to the current worktree's `.githooks/pre-push`, so a guard or `pre-push.local` from a removed worktree never runs (DL137).
