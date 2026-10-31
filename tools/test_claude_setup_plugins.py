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
    for e in errors:
        print("FAIL:", e)
    print(f"{len(names)} plugins checked, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
