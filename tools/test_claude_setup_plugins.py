#!/usr/bin/env python3
"""Every plugin in the marketplace must be in the claude-setup settings template
and named in the SKILL.md table, so a new plugin cannot be forgotten. No network."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "claude/plugins/project-setup/skills/claude-setup"


def main():
    names = [p["name"] for p in json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"]]
    enabled = json.loads((SKILL / "assets/.claude/settings.json").read_text())["enabledPlugins"]
    skill = (SKILL / "SKILL.md").read_text()
    errors = []
    if not names:
        errors.append("marketplace lists no plugins")
    for n in names:
        key = n + "@{{MARKETPLACE}}"
        if enabled.get(key) is not True:
            errors.append(f"settings template lacks {key}: true")
        if f"`{n}`" not in skill:
            errors.append(f"SKILL.md does not name `{n}`")
    for key in enabled:
        if key.split("@")[0] not in names:
            errors.append(f"settings template names {key}, not in the marketplace")
    if "--scope project" not in skill:
        errors.append("SKILL.md does not install plugins with --scope project")
    if "~/.claude/settings.json` `enabledPlugins.\"luismc-transcript-folds" in skill:
        errors.append("SKILL.md still wires transcript-folds at user level")
    if "extraKnownMarketplaces" not in skill:
        errors.append("SKILL.md does not write extraKnownMarketplaces")
    for offer in ("docs", "design system", "delivery", "project record", "specs",
                  "CI checks workflow", "repo gates", "auth"):
        if f"**{offer}**" not in skill:
            errors.append(f"SKILL.md status scan does not name the {offer} offer")
    for q in ("**Enforce**", "**Delivery mode**", "**CI**", "**Other setups**"):
        if q not in skill:
            errors.append(f"SKILL.md lacks the grouped question {q}")
    if "claude-setup status" not in skill:
        errors.append("SKILL.md lacks the status mode")
    tpl = SKILL / "assets/ci/dev-standards.yml"
    if not tpl.exists():
        errors.append("workflow template assets/ci/dev-standards.yml is missing")
    elif "docs_check.py\" --strict" not in tpl.read_text():
        errors.append("workflow template does not run docs_check.py --strict")
    for e in errors:
        print("FAIL:", e)
    print(f"{len(names)} plugins checked, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
