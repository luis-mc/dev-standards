#!/usr/bin/env python3
"""DL33: the five setup skills follow the setup pattern (section 13 of
docs/features/delivery/shared-self-hosted-runners.md). Each must contain the plan
step, the step lines rule, the safe-to-run-again rule and the three summary
headings Done, Left for you, What you can do now. No network."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = [
    "claude/plugins/project-setup/skills/claude-setup/SKILL.md",
    "claude/plugins/docs/skills/docs-setup/SKILL.md",
    "claude/plugins/docs/skills/design-system-setup/SKILL.md",
    "claude/plugins/project-setup/skills/tech-stack-setup/SKILL.md",
    "claude/plugins/project-setup/skills/auth-setup/SKILL.md",
]
PHRASES = ("plan first", "one line per step", "safe to run again")
HEADINGS = ("**Done**", "**Left for you**", "**What you can do now**")


def main():
    errors = []
    for rel in SKILLS:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"{rel} is missing")
            continue
        text = path.read_text()
        low = text.lower()
        for ph in PHRASES:
            if ph not in low:
                errors.append(f"{rel} lacks the setup pattern rule '{ph}'")
        for h in HEADINGS:
            if h not in text:
                errors.append(f"{rel} lacks the summary heading {h}")
    for e in errors:
        print("FAIL:", e)
    print(f"{len(SKILLS)} skills checked, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
