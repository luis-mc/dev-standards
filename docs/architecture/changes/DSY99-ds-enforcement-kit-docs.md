---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
---
`design_system.py guards --stack typescript-vitest-kit` copies an enforcement kit for projects that use the design system (TypeScript and Vitest only, D243): a no-app-CSS source scan, a DOM layout checker (360, 393 and 1300 px) and a wizard behaviour harness that requires the ten wizard states (D237, D244), each with a ratchet list that only shrinks. `design_system.py brief` writes and refreshes the UI brief checklist as a marked block in `AGENTS.md` and the pull request template (D239). The design-system-setup skill offers the kit by default in its plan when the project has a numbered version (D234) and asks for `design_system.app_paths` and `shared_paths` (D232).
