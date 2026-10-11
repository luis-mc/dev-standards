---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
change: major
---
New requirement STACKSPEC §13.7 (a MUST): a product that ships a packaged program has CI start the packaged form and wait for a readiness signal from the program and from every worker it starts, failing when one does not come up; the tracks get a `package.yml` workflow (path-filtered, never for docs-only merges, startable by hand) and a `smoke.json` declaration, and a new `smoke_packaged.py` runs the check. Build-artifact workflows run only when their inputs change (§13.1, SHOULD). `cleanup.py --pr N` appends a delivery log, the time to live of each change split into waiting, testing and queueing, to the train's release notes through the new `delivery_log.py`, whose `live` command the deploy calls (§13.6, SHOULD).
