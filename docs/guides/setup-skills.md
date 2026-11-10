---
title: What the setup skills do and what you can do after
type: how-to
---
# What the setup skills do and what you can do after

Use this guide to see, before you run a setup, what it will do, and what you have after it. The pattern is in [shared runners, section 13](../features/delivery/shared-self-hosted-runners.md). The feature pages are [project setup](../features/project-setup/spec.md) and [docs](../features/docs/spec.md).

## How every setup behaves

Every setup follows the same five parts.

1. **Plan first.** It shows what it will install, configure and write, what changes outside the repository, what needs you, and about how long it takes. It changes nothing before your yes.
2. **It does the work.** After the yes it runs every install and configuration it can. It leaves to you only what it cannot do: an administrator shell, a web setting, a sign-in, a secret. Each has exact steps and a check after.
3. **One line per step.** You see what it is doing, then done, or failed with the reason and the fix.
4. **Three-part summary.** *Done* (what changed, with paths), *Left for you* (numbered steps), *What you can do now* (commands and features, each with an example).
5. **Safe to run again.** A second run says what is already set and changes only what is missing.

```mermaid
flowchart LR
  plan[Plan] --> yes{Your yes}
  yes -->|no| stop[Nothing changed]
  yes -->|yes| run[Runs each step<br/>one line per step]
  run --> sum[Done / Left for you /<br/>What you can do now]
  sum -.->|run again| plan
```

## claude-setup

Applies the Claude Code configuration to the project and/or your user folder, turns on the eight plugins, installs the missing ones, then runs the setups you pick.

```mermaid
flowchart TD
  a[Ask target and offers] --> b[Plan: files, plugins, outside-repo writes]
  b --> c{Yes?}
  c -->|yes| d[Write settings, rules, hooks, status line]
  d --> e[Install missing plugins]
  e --> f[Run picked setups and audits]
  f --> g[Verify]
  g --> h[Done / Left for you / What you can do now]
```

After it: `/luismc-project-setup:claude-setup status` shows what is set, `/luismc-docs:docs-check` checks the docs, `/luismc-docs:spec-new` writes a spec, `/luismc-audits:security-audit` audits security, `ctrl+x d` toggles syntax highlighting. Reload with `/reload-plugins`.

## docs-setup

Lays out `docs/` to DOCSPEC, or moves an existing repo with `git mv` (never deletes).

```mermaid
flowchart TD
  a[migrate dry run or init plan] --> b{Yes?}
  b -->|yes| c[init or migrate --apply]
  c --> d[Write apps and topics in docs.json]
  d --> e[docs_index build and docs_check]
  e --> f[Done / Left for you / What you can do now]
```

After it: `/luismc-docs:docs-check`, `/luismc-docs:docs-index` (then open `docs/index.html`), `/luismc-docs:feature-spec-new`, `/luismc-docs:docs-note`.

## design-system-setup

Creates `docs/design-system/` with a draft, a review gallery and guard tests. Only you approve a version.

```mermaid
flowchart TD
  a[status and styles] --> b[Plan] --> c{Yes?}
  c -->|yes| d[init, guards, edit CONFIG and test runner]
  d --> e[visuals and check]
  e --> f[Done / Left for you: approve / What you can do now]
```

After it: `design_system.py status`, `design_system.py visuals` after a token change, `design_system.py check`, and `promote` when you approve.

## tech-stack-setup

A wizard picks a coherent stack, then generates the repository, CI, hooks and a Stack Profile.

```mermaid
flowchart TD
  a[Profile and role questions] --> b[Consequence review]
  b --> c[Provisioning ledger]
  c --> d[Plan] --> e{Yes?}
  e -->|yes| f[Generate in order, one line per step]
  f --> g[Verify with Mode 2]
  g --> h[Done / Left for you / What you can do now]
```

After it: `pnpm dev`, `pnpm test`, the branch gate (`python3 scripts/delivery/branch_gate.py --no-publish`) and `/luismc-project-setup:auth-setup`.

## auth-setup

Builds authentication to AUTHSPEC, or audits an existing build. It refuses until `tech-stack-setup` has run.

```mermaid
flowchart TD
  a[Preflight] --> b[Interview] --> c[Plan] --> d{Yes?}
  d -->|yes| e[Build in order, run the test gate]
  e --> f[Mode 2 check]
  f --> g[Done / Left for you / What you can do now]
```

After it: the auth endpoints in `apps/api`, the auth test suites with `pnpm test`, and an audit any time with `/luismc-project-setup:auth-setup`.
