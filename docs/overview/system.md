---
id: system
title: How the parts fit
type: explanation
owner: owner
last_verified: 2026-10-31
---
# How the parts fit

## Context

The owner installs plugins from the marketplace into Claude Code. Claude Code then works inside the owner's project repositories, which use GitHub for pull requests and CI. One status page is published to claude.ai.

```mermaid
flowchart LR
  owner[Owner]
  cc[Claude Code<br/>sessions and agents]
  ds[dev-standards<br/>marketplace repository]
  proj[Consuming project<br/>repositories]
  gh[GitHub<br/>pull requests and CI]
  cai[claude.ai<br/>artifacts]

  owner -->|installs plugins, sets standards| ds
  owner -->|reads status| cai
  owner -->|gives tasks| cc
  ds -->|plugins and specs| cc
  cc -->|edits files, opens pull requests| proj
  proj -->|pushes, CI runs| gh
  cc -->|publishes Full Progress| cai
```

## Containers

Inside dev-standards, the marketplace lists eight plugins. Hooks and scripts act on the consuming project's files, its `docs/` and its `.delivery/` ledger.

```mermaid
flowchart TB
  subgraph ds[dev-standards repository]
    mk[Marketplace<br/>.claude-plugin/marketplace.json]
    specs[Shipped specs<br/>ARTIFACTSPEC, DOCSPEC, STACKSPEC, AUTHSPEC, DELIVERYSPEC]
    tools[tools/ and tests<br/>spec lint, change notes, CI areas]
    subgraph plugins[Plugins]
      ps[project-setup]
      art[artifacts]
      dlv[delivery]
      docs[docs]
      spc[specs]
      aud[audits]
      agt[agents]
      tf[transcript-folds]
    end
  end
  subgraph proj[Consuming project repository]
    code[Code and CI workflows]
    pdocs[docs/ and AGENTS.md]
    rec[Artifacts record<br/>docs/project/]
    led[Ledger<br/>.delivery/ledger.json]
  end
  gh[GitHub CI]
  cai[claude.ai artifact]

  mk --> plugins
  specs --> ps
  specs --> art
  specs --> dlv
  specs --> docs
  ps -->|generates| code
  ps -->|writes Stack Profile| pdocs
  docs -->|checks, folds| pdocs
  art -->|renders| rec
  art -->|publishes| cai
  dlv -->|records and enforces| led
  code --> gh
  gh -->|run results| dlv
  tools -->|lint specs in CI| gh
```

## Data flows

**Install.** The owner adds the marketplace and installs plugins. Claude Code copies each plugin and reads its skills, hooks and agents.

**Set up a project.** `claude-setup` writes Claude Code settings and rule files. `tech-stack-setup` generates the repository, its CI and its delivery scripts, then records the spec versions in a Stack Profile. `auth-setup` builds on that.

**Deliver work.** An agent works on a short-lived task branch and runs its gate. The orchestrator joins branches into a release, opens one ready pull request, and merges at green CI. The delivery hooks read and write the ledger at each step, then require cleanup after the merge.

**Show status.** Each task change goes into the artifacts record through a script. Hooks queue changes from pull request, CI and deploy events. At the end of a turn, Full Progress is rendered and published to claude.ai. Feature artifacts stay as local HTML files.

**Keep docs true.** A task changes the code, the feature spec and adds a change note. The docs check compares code and docs. The release fold turns the notes into version bumps.
