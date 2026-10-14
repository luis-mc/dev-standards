# DS71: claude-setup wires luismc-delivery; rules and config

Branch `DS71-setup-delivery-wiring` (from `DS67-delivery-integration`). Contract: `docs/specs/delivery/DELIVERYSPEC.md`, section 5 (D2, D7, D8, D9) overrides.

## Plan
1. Report (this file).
2. Assets: `delivery-config.json` template, rules re-tagged to DL/Q ids, new `delivery-timing.md`, settings template.
3. `claude-setup/SKILL.md`: enable `luismc-delivery`, write `.delivery/config.json`, `.gitignore` entry, retire `no-tomorrow.mjs`, memory-to-rule map (D7).
4. tech-stack-setup `.githooks`: `commit-msg` (DL-74), conflict-marker check in `pre-commit` (DL-24).
5. Marketplace entry, README section, rule-tag test accepting DL/Q ids checked against DELIVERYSPEC.

## Not in scope
The plugin itself (`claude/plugins/delivery`, DS68-DS70). The marketplace entry points at it before it exists on this branch.

## Progress
(updated per step)
