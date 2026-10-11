# Test-cost train (TC6)

Source: `docs/artifacts/feature-test-and-validation-cost.html` (decisions D1 to D8). One integration branch, `TC6-integration`; three agent branches cut from it, each owning its files. Nobody edits a file another branch owns.

| Branch | Tasks | Owns |
|---|---|---|
| `DS43-ci-scoping` | DS43, DS44, TC1, TC4 | `.github/workflows/*` (new nightly workflow included), `tools/ci_areas.py` (new) and its test |
| `TC2-mutants-and-cleanup` | TC2, DS48, DS45 (join part) | `tools/test_delivery_gate.py`, `tools/test_delivery_cleanup.py`, `.../tooling/shared/scripts/delivery/{cleanup.py,join.py,CONTRACT.md}`, STACKSPEC `invariants.md` |
| `TC5-record-push-once` | TC5, TC3 | `claude/plugins/artifacts/**`, `tools/test_project_artifacts*.py`, `tools/test_render_artifacts.py` |
| `TC6-integration` (orchestrator) | DS45 (rule text), this file | `claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/agents-and-integration.md`, `.gitignore` |

Shared rules:

- **Areas (DS43).** spec-lint becomes one job per area: `specs` (spec_check, templates, AUTHSPEC, ARTIFACTSPEC numbering), `delivery` (gate, CI scripts, cleanup, prune, change notes, preflight), `artifacts` (renderer, commands, hooks), `profiles` (model profiles). A first job, `areas`, prints which areas a change touches with `tools/ci_areas.py`; a change to a shared path (`.github/workflows/spec-lint.yml`, `tools/ci_areas.py`, `tools/change-notes.json`, any `tools/*common*`) runs every area.
- **Mutants (TC1).** Each suite with a mutation pass keeps `--no-mutants`. In a PR, the `delivery` job passes it unless the change touches `assets/tooling/shared/scripts/delivery/**`, `assets/tooling/shared/.githooks/**` or the suite file itself. A nightly workflow (`nightly.yml`, cron on `main`) runs every area with mutants.
- **Fail fast (TC2).** In mutant mode a scenario stops at its first failed check. A crash still counts as caught; an uncaught mutant still fails loudly.
- **Main after merge (DS44).** On push to `main`, skip every area when the merge differs from the tested PR head only under `docs/artifacts/` (reuse the shipped `ci_skip_check`).
- **Record pushes (TC5).** Writing commands commit the record but do not push. A push happens at the end of the turn (end-of-turn hook), in `pending` before it lists anything, and before `gh pr create|merge|ready` (after-command hook sees those first; a PreToolUse check if needed). Push retries and refusals keep their exit codes.
- **Versions.** Never edit a `**Version:**` line, a change log or a `plugin.json` version: add a change note in `docs/specs/changes/<task>-<slug>.md` (`docs/specs/changes/README.md`). Expected: luismc-artifacts minor (ARTIFACTSPEC minor), luismc-project-setup minor, STACKSPEC minor only if `invariants.md` text changes.
- **Testing (DS45).** Run locally only the suites for files you changed, with `--no-mutants`, no Docker, no branch CI runs. Stop only processes you started. The ready PR's CI is the one full run.
