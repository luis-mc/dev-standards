---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
claude-setup enables `luismc-delivery`, writes `.delivery/config.json` and ignores `.delivery/`, retires the `no-tomorrow.mjs` Stop entry, reports a memory-to-rule map, and ships `delivery-timing.md` with every rule line tagged to its DELIVERYSPEC id; tech-stack-setup adds the `commit-msg` (DL-74) hook and a conflict-marker check in `pre-commit` (DL-24).
