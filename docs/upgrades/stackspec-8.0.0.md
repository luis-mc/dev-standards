# Upgrade to STACKSPEC 8.0.0

Released with luismc-project-setup 14.0.0 and luismc-artifacts 1.4.0. Paste the prompt below into Claude Code in the project to upgrade.

```
dev-standards released STACKSPEC 8.0.0 (luismc-project-setup 14.0.0, luismc-artifacts 1.4.0).

1. Update the plugins: `claude plugin marketplace update dev-standards`, then
   `claude plugin update luismc-project-setup@dev-standards` and
   `claude plugin update luismc-artifacts@dev-standards` at every scope where they are installed
   for this project (user and project); check with `claude plugin list`. Restart Claude Code.
2. Run /luismc-project-setup:tech-stack-setup in audit mode against this repository and apply its 8.0.0 items:
   - If this product ships a packaged program (single executable, installer, app bundle, container image):
     add scripts/delivery/smoke.json and the track's package.yml smoke job (STACKSPEC §13.7, a MUST).
     If it ships none, it conforms as it stands.
   - Copy the new delivery scripts and hooks (gate_verify inert paths, quick join check, train freeze in pre-push,
     runner-health warnings, delivery_log.py) and add `inert_paths` / `lockfile_scope` to gate.json.
   - Make build-artifact workflows path-filtered so docs-only merges never build.
   - Have the deploy job run `python3 scripts/delivery/delivery_log.py live --pr <N>` after its production smoke test.
3. Run /luismc-project-setup:claude-setup so the project's agents rule picks up
   "agents test only what they touch" and the area-only branch CI run.
4. Run any status change once (or `render`) so the artifact pages pick up the At a glance block, then publish
   Full Progress once and check it with /luismc-artifacts:project-artifact-check.
   Shorten any lede that check warns about to one or two sentences.
Change the Stack Profile's claimed version to 8.0.0 only after the audit passes.
```

## Only luismc-artifacts 1.4.0

For a project that uses the artifacts plugin but has not yet taken STACKSPEC 8.0.0, steps 1 (the artifacts plugin only) and 4 are enough.
