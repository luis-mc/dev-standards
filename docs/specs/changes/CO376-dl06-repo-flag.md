---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: patch
---
DL-06 honours the target repo of `gh pr merge`: -R/--repo, --repo=, and a full PR URL name the repo whose PR head and workflow runs are checked. A repo the ledger does not track is judged by that repo's own CI runs for the PR head (all completed, all successful, none pending); the project's own repo keeps the ledger decision. One shared parser (hooklib.gh_target) also serves the PostToolUse recorder, which no longer marks a same-numbered train of another repo merged.
