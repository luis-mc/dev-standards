# DS299: folder structure review

Read-only review of `main` on 2026-11-27. No repo file was moved or edited. IDs S1 and up are proposals. Unused files are in `ds298-unused.md` (U1 and up).

## Summary

- The layout is mostly sound. Each plugin is self-contained, naming is consistent (snake_case Python, kebab-case for everything else), and DOCSPEC folders match `docs/` except for the gaps DS298 lists.
- There are four real problems, plus one moderate one:
  1. Tests have two homes. 57 `tools/test_*.py` files test plugin code, next to 190 plugin `tests/` files. 11 of the tools tests and the whole `project-setup/tests/` folder never run in CI (see DS298 U5 to U7).
  2. Two of the five binding specs are named by topic (`invariants.md`, `authentication.md`) and hidden under `skills/*/references/`. The other three are `<specid>.md` under `<plugin>/references/`.
  3. Plugin-run scripts live in skill `assets/` folders (`spec_check.py`, `preflight.py`, `check_stack.py`, `ci_pin.py`). There, "assets" means "copied into a project".
  4. `clarifying-questions.md` exists twice, byte for byte. A test keeps the copies equal, and a project gets the text twice in each session.
  5. Moderate: one stack's files are split between two plugins (`delivery/templates/<track>/` and `tech-stack-setup/assets/tooling/<track>/`). The split is on purpose (DL15) and documented, but the tooling README tree is out of date.
- One plugin skeleton and a placement rule for each kind of file are proposed below.
- Ranked by value against churn: S1 (wire every test folder into CI), S2 (one copy of the question rules), S3 (move `vitest_shim` into the docs plugin), S4 (flatten `scripts/artifacts/`), S5 (spec names and place), S6 (scripts out of skill assets), S7 (tests next to their code), S8 (behaviour test names, new tests only), S9 (tooling README).
- Paths that projects cite, which must not move without a shim and a STACKSPEC/claude-setup note: `claude/plugins/docs/scripts/`, `claude/plugins/docs/skills/spec-check/assets/spec_check.py`, `claude/plugins/docs/.claude-plugin/plugin.json`, every installed `scripts/delivery/<name>` and `.claude/rules/<name>.md`, and `docs/guides/agent-delivery-details.md`. Projects cite the specs by ID and version, not by path. So S5 is safe for projects, but not for this repo's CI and tests.
- Requirement IDs, section numbers and `**Version:**` lines are untouched by every proposal. A spec text edit gets a change note; the fold writes versions.
- Would not do: rename the 185 task-ID tests, rename hook scripts, merge the per-stack template trees, move `schemas` out of `delivery/references/`, rename the shell scripts that projects carry, or split `docs/features/` by plugin.

## 1. What is there today

### Repository root

| Path | Role | Fits? |
|---|---|---|
| `README.md`, `AGENTS.md` | the entry point and agent rules (DOCSPEC §2.1) | yes |
| `.claude-plugin/marketplace.json` | lists six plugins | yes |
| `.claude/` (`settings.json`, `suites.json`, `artifacts.json`, `agents/Explore.md`) | this repo's own Claude settings (dogfood) | yes |
| `.delivery/config.json`, `.githooks/`, `.gitleaks*`, `.gitattributes` | this repo's own delivery and git settings | yes |
| `.github/workflows/` (6) | this repo's CI | yes |
| `tools/` | this repo's own CI tools (`ci_areas.py`, `plugin_smoke.py`, `authspec_check.py`, `template_build_check.py`, two JSON configs) **and** 57 tests, most of them for plugin code | mixed (S7) |
| `docs/` | DOCSPEC docs and the record (`docs/project`) | yes, with DS298 U3 and U12 |

There is no root `scripts/` folder, and none is needed. A root `scripts/` would compete with `tools/` and with the `scripts/delivery/` that projects get.

### Plugins

| Plugin | Folders |
|---|---|
| agents | `.claude-plugin`, `agents/` |
| audits | `.claude-plugin`, `skills/` |
| delivery | `.claude-plugin`, `README.md`, `commands/`, `hooks/`, `references/` (spec, two JSON schemas, compat JSON, brief template, design gate, asset names), `rules/`, `scripts/` (21), `templates/` (`shared`, `ts`, `go`, `rust`, `dotnet`, `lifecycle`, `ci-snippets`), `tests/` (148 + fixtures) |
| docs | `.claude-plugin`, `README.md`, `design/`, `hooks/`, `references/` (DOCSPEC, ARTIFACTSPEC), `rules/`, `schemas/`, `scripts/` (34 + `scripts/artifacts/` with one file), `skills/` (13; `spec-check/assets/spec_check.py`, `spec-new/assets/spec-template.md`), `templates/`, `tests/` (38), `vendor/` |
| project-setup | `.claude-plugin`, `hooks/`, `scripts/` (1), `skills/` (`auth-setup/references/authentication.md`, `tech-stack-setup/references/invariants.md`, `assets/` with templates **and** the scripts `check_stack.py`, `preflight.py`, `ci_pin.py`), `tests/` (4, not run by CI) |
| transcript-folds | `.claude-plugin`, `hooks/` (TypeScript mod: `transcript_folds.tsx`, `fold/*.ts`), `tests/` (`*.test.ts`), `types/` |

### Where the binding specs live

| Spec | Path | Named by |
|---|---|---|
| DELIVERYSPEC | `claude/plugins/delivery/references/deliveryspec.md` | spec ID |
| DOCSPEC | `claude/plugins/docs/references/docspec.md` | spec ID |
| ARTIFACTSPEC | `claude/plugins/docs/references/artifactspec.md` | spec ID |
| STACKSPEC | `claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md` | topic, inside a skill |
| AUTHSPEC | `claude/plugins/project-setup/skills/auth-setup/references/authentication.md` | topic, inside a skill |

There are three more contract documents: `delivery/templates/shared/scripts/delivery/CONTRACT.md` (1126 lines, shipped into projects), `delivery/templates/lifecycle/CONTRACT.md` and `docs/architecture/lifecycle-contract.md`. Each has one clear job, so they are not duplicates.

### Tests

| Home | Files | Named by task ID | Run by CI |
|---|---|---|---|
| `tools/test_*.py` | 57 | 21 (`test_artifacts_<id>`, `test_dl263_ci_pin`) | 46. The other 11 only through `.claude/suites.json` (DS298 U5, U6). |
| `claude/plugins/delivery/tests/` | 148 | 131 | yes (`unittest discover`) |
| `claude/plugins/docs/tests/` | 38 | 29 | yes (`unittest discover`) |
| `claude/plugins/project-setup/tests/` | 4 | 4 | **no** (DS298 U7) |
| `claude/plugins/transcript-folds/tests/` | 7 `*.test.ts` | 0 | yes (`node --test`) |

By CI area, the tools tests split like this: about 23 are artifacts tests (docs plugin code), 19 delivery, 7 profiles (mostly project-setup), 4 specs and 2 docs. Only `test_ci_areas`, `test_plugin_smoke` and `test_authspec_check` test a `tools/` script. `test_rule_tags` checks rule files across plugins.

### Copies of one concept

| Concept | Copies | Kept in step by |
|---|---|---|
| Question rules | `delivery/rules/clarifying-questions.md` (the SessionStart hook injects it every session) and `project-setup/skills/claude-setup/assets/.claude/rules/clarifying-questions.md` (claude-setup writes it into projects). Identical bytes. | `delivery/tests/test_questions.py`, `tools/test_questions_stop.py`, `tools/test_rule_tags.py`. project-setup R5.15 says "both copies". |
| Explore agent | `.claude/agents/Explore.md` and the claude-setup asset. Identical. | `tools/test_model_profiles.py`. This is dogfood, which is fine. |
| Per-stack files | `delivery/templates/<track>/` (CI workflows, `gate.json`, `smoke.json`) and `tech-stack-setup/assets/tooling/<track>/` (lint, guards, toolchain) | The tooling README (DL15) explains it. Its tree still lists `pre-push` and `commit-msg` under `tooling/shared/.githooks/`, but they live in `delivery/templates/shared/.githooks/`. |
| Git hooks for a project | `pre-commit` from project-setup, `pre-push` and `commit-msg` from delivery | the same DL15 split |
| Test helpers | `delivery/tests/_helpers.py` and `docs/tests/_helpers.py` (they differ) | none needed. Plugins stay independent. |
| Repo vs template configs | `.gitleaks.toml`, `.githooks/*`, `.delivery/config.json`, `.github/workflows/train-cleanup.yml` and the template versions | They differ on purpose: one is this repo's, one is a project's. |

### Naming

- Python files and modules: snake_case everywhere. No Python file has a dash.
- Skills, docs, JSON, YAML, TypeScript, CSS and folders: kebab-case. There are four exceptions: the shell scripts `agent_setup.sh` and `cloud_setup.sh`, `transcript_folds.tsx`, and the folders `tests/fixtures/ci_runs` and `tools/fixtures/vitest_shim`. The two shell scripts are installed into projects as `scripts/delivery/<name>`, so their names are project-cited.
- Go, Rust and Python guard files follow their language (`words_lint.go`, `words_lint.rs`); the TypeScript one is `words-lint.ts`. That is fine.
- Hook scripts: delivery names them after the event (`hook_stop`, `hook_pre_tool`, `hook_post_tool`, `hook_session_start`). docs mixes event names (`hook_stop`, `hook_session_start`) with phrases (`hook_end_of_turn`, `hook_after_command`, `hook_turn_start`), and keeps a second session-start hook in `scripts/artifacts/`. This comes from merging the artifacts plugin into docs (DS219).
- Tests: 185 of 247 Python test files are named after the task that added them (`test_dl105_gate_text.py`, `test_artifacts_ar59.py`). The name says when a test was written, not what it checks. To find the tests of `join.py`, you have to grep.

### `docs/` against DOCSPEC §2.1

| DOCSPEC folder | Here | Note |
|---|---|---|
| `overview/` (5 pages) | yes | |
| `features/` | 12 feature folders | Features are named by topic (`artifacts`, `specs`, `delivery-speed`, `test-cost`, `models`, `lifecycle`), not by plugin. DOCSPEC allows it. Keep. |
| `design-system/` | only `.gitkeep` | no UI here (U12) |
| `architecture/` | `decisions/`, `changes/`, `lifecycle-contract.md` | four MADRs are stale (U9) |
| `guides/` | 11 guides, empty `runbooks/` | four orphan guides (U20); `vm-checks.md` has no front matter |
| `reference/` | only `.gitkeep` | fine (U19) |
| `project/` | the record | U8, U11 |
| `archive/` | gone (DS293) | `docs/README.md` still describes it (U3) |
| `work/` | branch only | fine |

## 2. One plugin skeleton

```
claude/plugins/<name>/
├── .claude-plugin/plugin.json
├── README.md              what the plugin ships; one row per script
├── references/            binding specs only, named <specid>.md (lowercase spec ID)
│                          and reference pages they cite (asset names, brief template)
├── schemas/               JSON schemas the scripts validate against
├── rules/                 rule files a hook injects every session
├── commands/              slash commands
├── agents/                agent definitions
├── skills/<skill>/
│   ├── SKILL.md
│   ├── references/        reading for that skill only (never a binding spec)
│   └── assets/            files copied into a project, at their project-relative path
├── hooks/hooks.json       registration only; it points into scripts/ (or hooks/ for a TS mod)
├── scripts/               everything the plugin runs, flat: hook_<event>[_<topic>].py, CLIs, libs
├── templates/<track>/     files an installer writes into a project, at their project-relative path
├── design/, vendor/       optional runtime assets (CSS, third-party bundles with licence)
└── tests/
    ├── test_<module_or_behaviour>.py
    ├── _helpers.py
    └── fixtures/<topic>/
```

## 3. Placement rule for each kind of file

| Kind | Goes in | Rule |
|---|---|---|
| Binding spec (has a Spec ID and `**Version:**`) | `<plugin>/references/<specid>.md` | One per spec. Never inside a skill. |
| Feature spec, guide, MADR, change note | `docs/…` by DOCSPEC | Never in a plugin. |
| JSON schema | `<plugin>/schemas/` | New ones go here. The existing delivery schemas stay (see "would not do"). |
| Rule injected every session | `<plugin>/rules/` | One source. A setup skill does not also write a copy (S2). |
| Script the plugin runs (hook, CLI, checker) | `<plugin>/scripts/` | Flat. Even when one skill is the only caller. |
| File copied into a project | `skills/<skill>/assets/` (written by a skill) or `templates/` (written by an installer script) | Laid out at the project-relative path. Never a script the plugin itself runs. |
| Test of plugin code | `<plugin>/tests/` | Runs in CI through one `unittest discover` or `node --test` line per plugin. |
| Test of a `tools/` script, or a check that spans plugins | `tools/test_<script>.py` | Only these stay in `tools/`: `test_ci_areas`, `test_plugin_smoke`, `test_authspec_check`, `test_rule_tags`. |
| Test fixture | next to its tests, `tests/fixtures/<topic>/` | Named by topic, not task ID. |
| Repo-only CI tool | `tools/` | Never shipped. Never imported by a plugin. |
| Repo-only settings | `.claude/`, `.delivery/`, `.github/`, `.githooks/` | dogfood |
| Name | Python, Go, Rust: snake_case. Everything else: kebab-case. | A new test is named after the behaviour or module. Its task ID goes in the docstring. |

## 4. Proposals, ranked by value against churn

| ID | Change | Value | Churn | Projects affected? |
|---|---|---|---|---|
| S1 | Every test folder runs in CI: add `unittest discover` for `project-setup/tests`, plus the 11 suites-only tools tests (DS298 U5 to U7) | high | low (only `spec-lint.yml`) | no |
| S2 | One copy of the question rules | medium | low | yes: the installed `.claude/rules/clarifying-questions.md` |
| S3 | Move `tools/fixtures/vitest_shim/` to `claude/plugins/docs/tests/fixtures/vitest_shim/` | medium (a plugin test should not reach into `tools/`) | low | no |
| S4 | Flatten `docs/scripts/artifacts/hook_session_start.py` to `docs/scripts/hook_session_start_artifacts.py` | low to medium | low | no (resolved through `${CLAUDE_PLUGIN_ROOT}`) |
| S5 | STACKSPEC and AUTHSPEC to `project-setup/references/stackspec.md` and `authspec.md` | medium | medium | no (cited by ID); this repo's CI and tests yes |
| S6 | Scripts out of skill `assets/` into `project-setup/scripts/` (`check_stack.py`, `preflight.py`, `ci_pin.py`). Leave `spec_check.py` where it is. | medium | medium | `spec_check.py`: yes, so it stays |
| S7 | Plugin tests out of `tools/` into each plugin's `tests/` | medium | high (138 citing lines in 17 docs, plus CI, suites and `ci_areas.py`) | no |
| S8 | Behaviour names for new tests. Merge old task tests only when their module is already being changed. | medium over time | none now | no |
| S9 | Fix the tooling README tree. Add front matter to `vm-checks.md`. Link the four orphan guides. | low | very low | no |

### Move list

| ID | Old path | New path | References to update |
|---|---|---|---|
| S2 | `claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/clarifying-questions.md` | (deleted; `delivery/rules/clarifying-questions.md` is the only source) | claude-setup `SKILL.md` lines 34, 600 to 602 and 773. claude-setup must delete an identical old copy from the project, the same way docs R10.6 removes an old `project-artifacts.md`. `delivery/tests/test_questions.py` line 15. `tools/test_questions_stop.py` lines 123 and 124. `tools/test_rule_tags.py` line 42. `docs/features/project-setup/spec.md` R5.15 (rewrite, keep the ID). `deliveryspec.md` lines 325 and 352 (text). Root `README.md` line 73. Change notes for project-setup and delivery. **Check:** a non-project (user-level) target has no delivery hook, so it would lose the rule. Either keep writing it there only, or accept the loss. |
| S3 | `tools/fixtures/vitest_shim/{hooks,run,vitest}.mjs` | `claude/plugins/docs/tests/fixtures/vitest_shim/` | `claude/plugins/docs/tests/test_components.py` (the shim path). The release regenerates `docs/docs-map.json`. Test paths are exempt from plugin notes. |
| S4 | `claude/plugins/docs/scripts/artifacts/hook_session_start.py` | `claude/plugins/docs/scripts/hook_session_start_artifacts.py` | `docs/hooks/hooks.json`. `tools/ci_areas.py` rule `scripts/(artifacts/.*|…)`. `tools/test_ci_areas.py`. `tools/test_project_artifacts_hooks.py`. `artifactspec.md` §8 text, if it names the file. Its own imports (it sits one level deeper, so `sys.path` changes). Change note for docs. |
| S5a | `claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md` | `claude/plugins/project-setup/references/stackspec.md` | `spec_check.py` `_STACKSPEC` (line 101) and its docstring. `tools/change-notes.json` (`specs`, `changelog_headings`). `spec-lint.yml` `paths:`. `tools/ci_areas.py` (`TS + "/references/.*"`). `tools/test_ci_areas.py`. 4 `SKILL.md` mentions. `README.md`. Feature specs that cite the path. Change note for project-setup. Use `git mv` so `git log --follow` keeps the history. |
| S5b | `claude/plugins/project-setup/skills/auth-setup/references/authentication.md` | `claude/plugins/project-setup/references/authspec.md` | the same set, plus `spec-lint.yml` `env.AUTHSPEC`, `tools/authspec_check.py` and `tools/test_authspec_check.py` |
| S6a | `…/tech-stack-setup/assets/preflight.py` | `claude/plugins/project-setup/scripts/preflight.py` | `auth-setup/SKILL.md` line 25 (it already reaches across skills). `tech-stack-setup/SKILL.md`. `spec-lint.yml` `paths:`. `tools/ci_areas.py` (`TS + "/assets/preflight.py"`). `tools/test_preflight.py` |
| S6b | `…/tech-stack-setup/assets/check_stack.py` | `claude/plugins/project-setup/scripts/check_stack.py` | `tech-stack-setup/SKILL.md` lines 195, 266 and 742. `tools/ci_areas.py`. `tools/test_check_stack_rust.py` |
| S6c | `…/claude-setup/assets/ci_pin.py` | `claude/plugins/project-setup/scripts/ci_pin.py` | `claude-setup/SKILL.md` line 181. The comment header in `assets/ci/dev-standards.yml` (it tells owners to run `<claude-setup>/assets/ci_pin.py`; this is text in projects, so keep a one-line note). `tools/test_dl263_ci_pin.py` |
| S7 | `tools/test_artifacts_*.py`, `test_project_artifacts*.py`, `test_render_artifacts.py`, `test_ds_*.py`, `test_spec_check.py` | `claude/plugins/docs/tests/` | Run lines in `spec-lint.yml`. `.claude/suites.json` (its comment says "Every suite is tools/test_*.py"). `tools/ci_areas.py` RULES and `SUITE_MUTANTS` paths. `tools/test_ci_areas.py`. Proof tables in `docs/features/*/spec.md`, `artifactspec.md` and `docspec.md` (paths only, IDs unchanged). The `sys.path` and `ROOT` lines in each moved file. The old `.gitleaksignore` entries stay (keyed by commit). |
| S7 | `tools/test_delivery_*.py`, `test_artifact_prune.py`, `test_ci_speedups.py`, `test_shard_guard.py`, `test_smoke_packaged.py`, `test_session_guard.py`, `test_change_notes.py`, `test_kit_suite_sim.py` | `claude/plugins/delivery/tests/` | the same set. **Do the mutant suites last:** `test_delivery_gate.py`, `test_delivery_cleanup.py` and `test_change_notes.py` are wired into `--shard` jobs and `SUITE_MUTANTS`. |
| S7 | `tools/test_project_setup_fixes.py`, `test_setup_pattern.py`, `test_claude_setup_plugins.py`, `test_check_stack_rust.py`, `test_preflight.py`, `test_questions_stop.py`, `test_model_profiles.py`, `test_dl263_ci_pin.py` | `claude/plugins/project-setup/tests/` | the same set |
| S9 | (text) `tech-stack-setup/assets/tooling/README.md` tree | — | List only `pre-commit` under `shared/.githooks/`, and point to delivery for the other two hooks. |

### Paths projects cite: do not move

| Path | Cited by |
|---|---|
| `claude/plugins/docs/scripts/` | the project workflow `{{DOCS_SCRIPTS}}` (`assets/ci/dev-standards.yml`, filled and committed in each project); `cloud_setup.sh` `scripts_rel` |
| `claude/plugins/docs/skills/spec-check/assets/spec_check.py` | the project workflow `{{SPEC_CHECK}}`, filled and committed. This is why S6 leaves it in place. Moving it would need a forwarding stub for as long as projects pin older refs. |
| `claude/plugins/docs/.claude-plugin/plugin.json` | `ci_pin.py` `DOCS_JSON` (it reads the pin's version) |
| `scripts/delivery/<name>` in a project (`agent_setup.sh`, `cloud_setup.sh`, `ci_watch.py` and the rest) | `CONTRACT.md`, the agent rules, and project workflows. Renaming a template file renames it in every project on the next install. |
| `.claude/rules/<name>.md`, `docs/guides/agent-delivery-details.md` | the claude-setup assets and rule text that projects carry |
| `claude/plugins/delivery/templates/shared/scripts/delivery/change_notes.py` | the project `pre-commit` fallback (in practice this repo's) |
| Spec IDs, section numbers, requirement IDs, `**Version:**` lines | Stack Profiles, hooks and tests in projects (AGENTS.md). No proposal here touches them. |

## 5. What I would not do

- **Rename the 185 task-ID test files.** 114 spec lines cite plugin test paths and 138 cite `tools/test_*` paths. Renaming would rewrite those proof tables and blur `git log`, and nothing would work better. Use S8 instead.
- **Rename hook scripts to one pattern** (`hook_end_of_turn` to `hook_stop_artifacts`, and so on). The paths go through `${CLAUDE_PLUGIN_ROOT}`, but ARTIFACTSPEC §8 and many hook tests name them. The value is cosmetic. S4 is the only hook move worth making.
- **Merge `delivery/templates/<track>` with `tech-stack-setup/assets/tooling/<track>`.** The split follows who writes the file (the delivery installer or the setup skill). DL15 chose it, and both plugins must work alone (DOCSPEC R12.2 has the same principle). Fix the README instead (S9).
- **Move `config-schema.json` and `ledger-schema.json` to `delivery/schemas/`.** They are consistent with docs' `schemas/` only in name. The move touches the delivery scripts, tests and DELIVERYSPEC text, and gains nothing. Apply the rule to new schemas only.
- **Rename `agent_setup.sh` and `cloud_setup.sh` to kebab-case.** Projects carry them under these names.
- **Move the shipped specs into `docs/architecture/`.** They are part of the product a plugin ships, so they belong in the plugin. `docs/` describes dev-standards itself.
- **Create a root `scripts/` folder**, or split `tools/` into CI tools and tests subfolders. `tools/` gets small after S7, and that is enough.
- **Split `docs/features/` by plugin.** DOCSPEC sorts features by reader question, not by package.

## Order of work

1. S1, S9, S3 and S4 (one light branch each, or two together).
2. S2, with the user-level answer from the owner.
3. S5 and S6 together. One branch for project-setup, one change note, `git mv`.
4. S7, area by area (docs, then project-setup, then delivery), so each step runs only its own CI area. Leave the mutant suites to the end.
