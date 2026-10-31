---
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
change: minor
---
§13.5: the branch gate runs the always-on guards, then type check and lint of the touched packages and their dependents, then the test steps; a time limit never skips lint or types, the verifier refuses a result where a required step did not run, and the pre-push hook SHOULD also run lint and type check; §13.1 adds advice to run OS-neutral CI jobs on another runner in parallel when ready-PR CI shares one Linux runner.
