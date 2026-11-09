---
id: project-setup
title: Project setup (luismc-project-setup)
apps: [luismc-project-setup]
topics: [stack, auth, delivery, models, testing, ci]
status: live
version: 0.8.0
owner: agents
type: reference
code:
  - claude/plugins/project-setup/**
  - tools/test_preflight.py
  - tools/test_claude_setup_plugins.py
  - tools/test_setup_pattern.py
  - tools/test_authspec_check.py
  - tools/test_spec_check.py
  - tools/test_model_profiles.py
  - tools/test_rule_tags.py
  - tools/test_questions_stop.py
  - tools/test_project_setup_fixes.py
  - tools/test_check_stack_rust.py
last_verified: 2026-11-08
---
# Project setup (luismc-project-setup)

Two binding specs hold the rules this plugin builds to. Read them there. This page does not copy them.

- STACKSPEC: [invariants.md](../../../claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md)
- AUTHSPEC: [authentication.md](../../../claude/plugins/project-setup/skills/auth-setup/references/authentication.md)

## 1. In one paragraph

`luismc-project-setup` takes a repository from empty to production-ready. It has three skills, run in order. `tech-stack-setup` helps pick a compatible stack. It generates a repository to STACKSPEC, or audits an existing one. `auth-setup` builds authentication to AUTHSPEC on top of it. `claude-setup` configures Claude Code for the project or the user.

## 2. Why

A new product needs the same hard parts every time: a coherent stack, a gate that proves a branch is ready, authentication that survives erasure rules, and an agent set up to work the same way in every session. Done ad hoc, these drift. Rules in specs and generation in skills make drift measurable.

Goals: every option offered is compatible with earlier choices. The generated repository can be audited against the spec. Authentication is a separate step that can be reviewed.

Non-goals: choosing vendors for the user, and building authentication inside `tech-stack-setup`.

## 3. How it works

```mermaid
flowchart LR
  c[claude-setup<br/>agent config] -.-> p[(Project)]
  t[tech-stack-setup<br/>wizard then generate] --> p
  t -->|writes| sp[Stack Profile]
  sp --> pre{preflight.py}
  pre -->|stack present| a[auth-setup<br/>build or check]
  pre -->|missing| t
  a --> p
  t -->|audit mode| r[Conformance report and safe repairs]
```

1. `tech-stack-setup` interviews the user. After each answer, it filters the options in `assets/catalog/` so that only compatible ones remain. It shows the consequences. Then it generates the repository and a Stack Profile. The profile records the spec versions claimed.
2. `auth-setup` runs `preflight.py` first and refuses until the stack exists. It reads the Stack Profile and interviews the user for the decisions the spec will not default. Then it builds in dependency order. Its second mode audits an existing implementation.
3. `claude-setup` asks for project, user level or both. Project is preselected and marked (Recommended). Rules, `CLAUDE.md`, status line, output style, hook, model split and auto-compact env go to the project's `.claude/` by default. It turns on all eight plugins in the project's `enabledPlugins`, installs missing ones with `--scope project`, and adds `extraKnownMarketplaces` to the project's settings when the entry is missing. Only the transcript-folds chords stay in `~/.claude/keybindings.json`. It shows one batch plan and confirms once. Then it writes the settings, rules, hooks and status line. It never overwrites a hand-written `CLAUDE.md` or an existing settings key. It then asks every question of every offer in one grouped round: docs, design system, delivery, project record, CI, branch protection, other setups and three separate audits (security, compliance, performance). After the yes it runs the picked setups in the same session: the tech-stack-setup audit, auth-setup when repo gates exist, then each audit, holding a heavy step when memory is over 85% or CPU over 60%. For branch protection it reads the current protection, merges the dev-standards check and runs the PUT when the workflow has already run on the default branch. Otherwise it records `pending_protection: true` in `.delivery/config.json`. It never commits or pushes. Its final report ends with one numbered "Left for you" list, followed by the enforcement table, whose rows name the step that fixes them.

All three skills follow the setup pattern (plan first, do the work after a yes, one line per step, a summary with Done, Left for you and What you can do now, safe to run again). See [the setup skills guide](../../guides/setup-skills.md) for a flow of each and what you can do after.

## 5. Functional requirements

**R5.1** — `tech-stack-setup` offers only technologies compatible with the choices already made, and `check_stack.py --selection` verifies a selection against the catalog.

**R5.2** — `tech-stack-setup` generates for four tracks: TypeScript, Go, Rust and .NET. Each track has its own `gate.json`, `smoke.json` and CI workflows. They live in `luismc-delivery` (`templates/`), and `tech-stack-setup` calls the delivery installer at the end of its setup (see [delivery](../delivery/spec.md), R13.3).

**R5.3** — `tech-stack-setup` writes a Stack Profile that records the STACKSPEC version claimed and the vendor choices. It does not copy either spec into the project.

**R5.4** — `tech-stack-setup` in audit mode reports conformance section by section and shows a diff before any repair.

**R5.5** — `tech-stack-setup` does not build authentication. At the end, it asks whether to run `auth-setup`.

**R5.6** — `auth-setup` runs `preflight.py --require stack` before anything else and stops with the skill to run first when the stack is missing.

**R5.7** — `preflight.py` exits 0 when every requirement holds, 1 when one does not, and 2 on bad arguments.

**R5.8** — `auth-setup` reads the Stack Profile. Before it generates, it reports a claimed AUTHSPEC version that is older than the bundled one.

**R5.9** — `claude-setup` never overwrites an existing `CLAUDE.md` or an existing settings key. The two model-split keys are shown as a conflict when they hold a different model.

**R5.10** — Every skill's `model:` and `effort:` front matter matches its row in `assets/model-profiles.json`.

**R5.11** — Every rule line in the rule files `claude-setup` ships ends with a tag naming its check, or `advice`.

**R5.12** — The shipped STACKSPEC and AUTHSPEC have valid heading numbers, requirement IDs and references, and AUTHSPEC passes its own content checks.

**R5.13** — At user level, `claude-setup` installs `~/.claude/hooks/questions_stop.py` and adds it to `hooks.Stop` in `~/.claude/settings.json`, without removing another hook. The hook blocks a stop when the final reply asks the owner a question in plain text, lists options to pick, or says questions are parked, and the turn made no AskUserQuestion call. It enforces Q-1 and Q-2.

**R5.14** — The `questions_stop.py` hook counts an agent as running when its state is queued or running, or when it has an `eta`, no `done_at` and a state that is not done, empty, failed or stopped. When the parked-question check finds a running agent due within 60 minutes, the hook allows the stop and prints `Questions wait for the report of agent <task> (due within 60 minutes); do not ask now.` Plain-text questions (Q-2) still block. A missing or bad ledger adds no agents and the check carries on. (DL124)

**R5.15** — Both copies of `clarifying-questions.md` carry one rule line, in the same words: the hook can see an open question, and a `RemoteTrigger` `create` or `update` due in under 2 hours then draws a warning, never a block. (DL136)

**R5.16** — The pre-push hook exits 1 with `pre-push: node_modules is missing in this worktree; run pnpm install --frozen-lockfile here.` when `package.json` and `pnpm-lock.yaml` exist, `scripts/delivery/gate.json` has a command that starts with `pnpm `, and `node_modules` does not exist. The check runs after the `scripts/delivery` check and before the Python and guard steps. (DL130)

**R5.17** — `core.hooksPath` is shared by all worktrees. The pre-push hook compares its own folder with `<git rev-parse --show-toplevel>/.githooks`. If they differ and the current worktree has a `pre-push`, the hook runs that one with `exec`. The variable `PRE_PUSH_REEXEC` stops a loop. (DL137)

**R5.18** — `check_stack.py` accepts `{api: X, components: [rust]}` as well as `language`. A component is an id or a mapping with `id`, `parts`, `reason`, `build_matrix`, `cross_compile`, `licence_note`, `targets` and `windows_runner`. Host elimination applies to the API language only. An unknown component or part is an error. (DS196, D138)

**R5.19** — `check_stack.py` warns on: a Rust component with no recorded reason; a napi addon with no build matrix; a cross-compile target with no licence note; a Windows host-service with neither `cross_compile` nor `windows_runner`; a napi component on Vercel. `check_stack.py --catalog` checks the parts and pairings of the catalog. (DS196)

**R5.20** — The catalog gives `rust` the roles `api` and `component`. The `component` block has `requires_reason` and a `reason_prompt` that asks for a written reason only (D145), the parts `cli`, `host-service`, `library-napi` (needs a build matrix) and `library-wasm`, and the later parts `worker` and `media` (D139). `roles.yaml` has the asked role `native_components` (multi-select, default none). `bundles.yaml` has `component_pairings`: any API language and any host; a host-service needs a Windows build option; wasm on Cloudflare is supported; napi on Vercel warns. Rust stays out of every default and every bundle recommendation. (DS196)

**R5.21** — `tech-stack-setup` Phase 1 asks whether any part of the product runs on a user's or operator's machine. Phase 3 binds `native_components`: the parts, the written reason (D145), the target OSes and which ships first, the napi build matrix, the cross-compile licence note, the Windows option (cross-build on Linux with cargo-xwin after the licence is accepted once and recorded, or a Windows runner; D144), and a signing row in the provisioning ledger. Phase 7 generates the Cargo workspace layout, and Mode 2 audits it. No section is renumbered. (DS197)

**R5.22** — `assets/tooling/rust/` ships `Cargo.toml` (resolver 2, `crates/*` members, `[workspace.package]`, `[workspace.dependencies]`, a fixed release profile), `rust-toolchain.toml` (exact `1.91.0`, minimal profile, rustfmt and clippy, empty targets), `rustfmt.toml` and `deny.toml` (advisories, bans, licenses, sources). The wizard copies them to the repository root beside `crates/guards`. Every cargo command uses `--locked`, and CI installs the exact toolchain version. The tooling README maps each STACKSPEC invariant to its Rust command. (DS198)

## 6. Non-functional requirements

**R6.1** — `claude-setup` asks which target before reading or writing, and applies one batch after one confirmation.

**R6.2** — The model-profile default is medium effort for every model (the owner's default). The profile table is the one place that sets it.

## 7. Design

```mermaid
flowchart TB
  subgraph skills[Skills]
    cs[claude-setup]
    ts[tech-stack-setup]
    as[auth-setup]
  end
  ts --> cat[assets/catalog<br/>roles, bundles, tech]
  ts --> chk[check_stack.py]
  ts --> tool[assets/tooling<br/>shared and per-track]
  ts --> sp[assets/stack-profile.md]
  ts --> inv[references/invariants.md STACKSPEC]
  as --> pre[preflight.py]
  as --> auth[references/authentication.md AUTHSPEC]
  cs --> ca[assets: settings, rules, hooks, statusline, model-profiles.json]
```

- The catalog is data, not requirements. STACKSPEC defines a `CHOICE` level. A choice is reported as recorded or unrecorded, never as violating.
- The shared delivery tooling (scripts and workflows in `luismc-delivery` `templates/`) is written into each generated repository by the delivery installer; the git hooks, linters and guards in `assets/tooling/` are copied by `tech-stack-setup`. Its rules and tests belong to [delivery](../delivery/spec.md) and [delivery-speed](../delivery-speed/spec.md). This page does not repeat them.
- The questions Stop hook (R5.13) never loops (`stop_hook_active` allows), ignores code blocks, inline code and quoted lines, lets a park through while agents of the wave still run (Q-5, a running agent in `.delivery/ledger.json`), and fails open on any error. It blocks a list only when the line above it reads as an offer to pick from (not "Files changed:"), and a reply that says there are no open questions passes. Its hook command runs `python3` when present and `python` only otherwise, so exit 2 reaches Claude Code. Turn it off with `CLAUDE_QUESTIONS_STOP=off` (shell or settings `env` block) or `"questionsStop": "off"` in `~/.claude/settings.json`.

```mermaid
flowchart TD
  S[Stop] --> A{stop_hook_active or off?}
  A -- yes --> OK[allow]
  A -- no --> B{AskUserQuestion in turn?}
  B -- yes --> OK
  B -- no --> C{plain question or options at end?}
  C -- yes --> X[block: ask in one batch]
  C -- no --> D{says parked or later?}
  D -- no --> OK
  D -- yes --> E{agents still run?}
  E -- yes --> OK
  E -- no --> X
```

- The per-skill model table, the effort-drift hook and how profiles are applied belong to [models](../models/spec.md).

## 8. Failure modes

- `auth-setup` without a stack: fails closed (`preflight.py` exits 1).
- `check_stack.py` without PyYAML: exits 2 with an install hint.
- `claude-setup` on a conflicting key: leaves the key and shows the conflict (fails safe, no silent change).
- `tech-stack-setup` audit mode: never touches what already conforms.

## 9. How it is proven

| Requirement | Test |
|---|---|
| R5.6, R5.7 | `tools/test_preflight.py` |
| R5.10, R6.2 | `tools/test_model_profiles.py` |
| R5.11 | `tools/test_rule_tags.py` |
| R5.13 | `tools/test_questions_stop.py` (the hook on recorded inputs and its wiring) |
| R5.12 | `tools/test_spec_check.py`, `tools/test_authspec_check.py` |
| R5.1 to R5.5, R5.8, R5.9, R6.1 | not covered by a test yet; see section 11 |

## 10. Decisions

| ID | Question | Chosen | Date |
|---|---|---|---|
| 0001-docs-rewrite | Keep STACKSPEC and AUTHSPEC IDs in the rewrite? | Yes, layout and wording only | 2026-10-31 |

## 11. Not built yet

NOT YET IMPLEMENTED: tests for the wizard's filtering and for `check_stack.py` (R5.1), for the four-track tooling (R5.2), for the Stack Profile (R5.3), for the audit mode (R5.4, R5.5, R5.8), and for the no-overwrite rule (R5.9). The skills are prompts, so these tests need a fixture repository. The seam is `tools/`, next to `test_preflight.py`.

## 12. Code map

Source: claude/plugins/project-setup/skills/tech-stack-setup/SKILL.md
Source: claude/plugins/project-setup/skills/tech-stack-setup/assets/check_stack.py
Source: claude/plugins/project-setup/skills/tech-stack-setup/assets/preflight.py
Source: claude/plugins/project-setup/skills/tech-stack-setup/assets/stack-profile.md
Source: claude/plugins/project-setup/skills/tech-stack-setup/assets/catalog/roles.yaml
Source: claude/plugins/project-setup/skills/auth-setup/SKILL.md
Source: claude/plugins/project-setup/skills/claude-setup/SKILL.md
Source: claude/plugins/project-setup/skills/claude-setup/assets/model-profiles.json
Source: claude/plugins/project-setup/skills/claude-setup/assets/.claude/hooks/questions_stop.py
Source: claude/plugins/project-setup/.claude-plugin/plugin.json

## Versions

Written by the release fold. Do not edit by hand.

| Version | Date | Release | What changed | Tasks |
|---|---|---|---|---|
| 0.8.0 | 2026-11-09 | RELEASE-71 | Stop hook counts agents with an ETA and no agent-done; says questions wait when one is due within 60 minutes. Clarifying-questions rule: a routine held for an owner answer is paused, never postponed by minutes.<br>DS196: Rust as a component role beside any API language; parts cli, host-service, library-napi, library-wasm; check_stack.py warnings. Spec text follows in DS203.<br>tech-stack-setup wizard text: machine-side question, native_components binding with written reason, napi build matrix, cross-compile licence and Windows build option, Rust workspace layout, Rust audit wording.<br>Adds R5.14 to R5.22: stop hook ETA parking, pre-push fixes, Rust as a component in the catalog, the wizard and the tooling assets. | DL124, DS196, DS197, DS203 |
| 0.7.1 | 2026-11-04 | RELEASE-42 | Questions Stop hook blocks a list only when the line above offers a choice, passes 'no open questions', and hook commands keep exit 2 (python3 if present, else python). | DS185 |
| 0.7.0 | 2026-11-04 | RELEASE-38 | claude-setup installs a user-level Stop hook (questions_stop.py) that blocks plain-text questions and parked questions, enforcing Q-1 and Q-2 (R5.13). | SO6 |
| 0.6.0 | 2026-11-04 | RELEASE-37 | claude-setup, tech-stack-setup and auth-setup follow the setup pattern: plan first, one line per step, and a Done, Left for you, What you can do now summary. | DL33 |
| 0.5.1 | 2026-11-02 | RELEASE-34 | R5.2 and the delivery tooling note: the CI and delivery templates moved to luismc-delivery. tech-stack-setup calls the delivery installer at the end of its setup. No requirement ID changed. | DL15 |
| 0.5.0 | 2026-11-02 | RELEASE-31 | claude-setup runs the picked setups and three separate audits, applies branch protection after reading current protection, and ends its report with a numbered Left for you list. | SO5 |
| 0.4.0 | 2026-11-01 | RELEASE-28 | claude-setup defaults to project level: config files go to the project's .claude/, plugins install with --scope project, and extraKnownMarketplaces is added when missing. | SO4 |
| 0.3.0 | 2026-11-01 | RELEASE-27 | Agents run the e2e specs of the screens they change: the gate records and verifies them, a pre-push check refuses an unrun e2e spec fix, and briefs say so (DELIVERYSPEC DL-86 to DL-89). | DS35 |
| 0.2.0 | 2026-11-01 | RELEASE-25 | claude-setup's model profiles list the design-system-setup skill under the mechanical profile (Sonnet, medium).<br>Workflow templates pin every action to a full commit SHA with the tag in a comment (rust-toolchain gets toolchain: stable). agent_setup.sh and the ci.yml secret scan no longer fall back to the release checksums file: with no pin they refuse and print the tools_pin.py command.<br>The artifact-prune REST fallback refuses a next-page URL on a foreign host, and the interim-record converter no longer uses eval.<br>claude-setup now offers to enforce docs, design system, delivery, project record and CI checks, and reports what each plugin enforces; claude-setup status reports only. | DOC17-model-profile, DS162, DS163, SO2 |
| 0.1.1 | 2026-11-01 | RELEASE-22 | Wording pass; requirements and IDs unchanged. | DS143 |
