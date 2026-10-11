---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
change: minor
---
The gate scopes more tightly (STACKSPEC §13.5): `gate.json` gains `inert_paths` (default `docs/**`), and `gate_verify.py` keeps a result valid when the base moved only by commits under those paths (`--strict-base` turns that off); a new `lockfile_scope` key lets a pnpm lockfile change count as a change to the packages whose dependencies moved instead of widening the whole gate (Go and .NET per-package lockfiles stop widening, Cargo.lock still widens); and without an `e2e_map` the end-to-end specs of the apps that import a changed shared UI package come from the workspace dependency graph.
