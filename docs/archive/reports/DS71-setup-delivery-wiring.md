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
- Done: delivery-config.json template; agents-and-integration, clarifying-questions (Q-1..Q-5, wizard and in-question context lines) re-tagged to DL/Q ids; new delivery-timing.md; settings template enables luismc-delivery; SKILL.md steps 1-5 (config, .gitignore, no-tomorrow retirement as a confirmed removal, D7 memory map, report only); commit-msg and pre-commit conflict-marker hooks (tried in a scratch repo: marker refused, clean commit passes, attribution refused only when no_attribution is true); marketplace entry and README section; tools/test_rule_tags.py now validates id tags against DELIVERYSPEC (4 new self-tests); change note (minor).
- Checks: rule-tags passed (60 lines, 4 files), model-profiles OK, ci-areas OK.
- Open: `claude/plugins/delivery` is absent on this branch until DS68-DS70 join, so the marketplace entry points at a folder that does not exist yet.
