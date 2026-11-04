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
    for q in ("**Enforce**", "**Delivery mode**", "**CI**", "**Branch protection**",
              "**Other setups**", "**Audits**"):
        if q not in skill:
            errors.append(f"SKILL.md lacks the grouped question {q}")
    for a in ("security audit", "compliance audit", "performance audit"):
        if a not in skill:
            errors.append(f"SKILL.md lacks the separate audit option {a}")
    if "run the picked setups" not in skill:
        errors.append("SKILL.md does not say picked setups are run")
    if "Left for you" not in skill:
        errors.append("SKILL.md lacks the Left for you list")
    for h in ("**Done**", "**What you can do now**"):
        if h not in skill:
            errors.append(f"SKILL.md lacks the summary heading {h}")
    for ph in ("plan first", "one line per step", "safe to run again"):
        if ph not in skill.lower():
            errors.append(f"SKILL.md lacks the setup pattern rule '{ph}'")
    read_at = skill.find("read the current protection first")
    put_at = skill.find("gh api -X PUT repos/<owner>/<repo>/branches/<default>/protection")
    if read_at < 0 or put_at < 0 or read_at > put_at:
        errors.append("SKILL.md does not read current protection before the PUT")
    if "inside this plan" in skill or "Only print it" in skill:
        errors.append("SKILL.md still hands setups over or only prints the command")
    if "claude-setup status" not in skill:
        errors.append("SKILL.md lacks the status mode")
    tpl = SKILL / "assets/ci/dev-standards.yml"
    if not tpl.exists():
        errors.append("workflow template assets/ci/dev-standards.yml is missing")
    elif "docs_check.py\" --strict" not in tpl.read_text():
        errors.append("workflow template does not run docs_check.py --strict")
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import test_setup_pattern  # DL33: the five setup skills follow the setup pattern
    if test_setup_pattern.main():
        errors.append("a setup skill breaks the setup pattern (see above)")
    import test_project_setup_fixes  # DS185: regression checks for the project-setup review findings
    if test_project_setup_fixes.main():
        errors.append("a project-setup fix regressed (see above)")
    for e in errors:
        print("FAIL:", e)
    print(f"{len(names)} plugins checked, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
