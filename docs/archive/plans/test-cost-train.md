> Superseded by [test cost spec](../../features/test-cost/spec.md). History only, not binding.

# Test-cost train (TC6)

Source: `docs/project/feature-test-and-validation-cost.html` (decisions D1 to D8). One integration branch, `TC6-integration`; three agent branches cut from it, each owning its files. Nobody edits a file another branch owns.

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

## Delivery speed, folded into this train (DL1 to DL10)

The plan is section 2 of `docs/project/feature-delivery-speed.html`; its decisions D1 to D9 are settled. STACKSPEC becomes **8.0.0** (DL9 adds a MUST), luismc-project-setup **major**. Three branches, cut from `TC6-integration` after DS43, TC2 and TC5 were joined:

| Branch | Tasks | Owns |
|---|---|---|
| `DL1-gate-scope-and-inert` | DL1, DL4 | `gate_verify.py`, `branch_gate.py`, `delivery_common.py`, the four tracks' `gate.json`, gate/verify/scope scenarios in `tools/test_delivery_gate.py` |
| `DL2-join-freeze-runners` | DL2, DL6, DL7 | `join.py`, `ci_watch.py`, `shared/.githooks/pre-push`, `fast_guards.py`, tech-stack-setup `SKILL.md` (runner question), join/hook scenarios in `tools/test_delivery_gate.py`, ci_watch cases in `tools/test_delivery_ci.py` |
| `DL5-ci-packaging-log` | DL5, DL8, DL9 | the tracks' `ci.yml` and other workflow templates, `cleanup.py`, `tools/test_delivery_cleanup.py`, `tools/template_build_check.py`, `.github/workflows/template-build.yml` |
| orchestrator | DL3, DL10 | the agents rule, dev-standards' own adoption |

Shared files: `CONTRACT.md` and STACKSPEC `invariants.md`: each branch edits only the paragraphs of its own tasks (DL1: §13.5 gate and trust; DL2: §13.6 join and freeze, §13.1 runner health; DL5: §13.1 build artifacts, the new packaged-program smoke test, delivery log). Add new scenarios and mutants to `tools/test_delivery_gate.py` at the end of the SCENARIOS and MUTANTS lists only, so joins merge cleanly. Change notes: one per branch, `spec:` invariants.md with `change: major` only on `DL5-ci-packaging-log` (DL9's MUST); the others `change: minor`.
