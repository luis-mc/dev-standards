---
id: lifecycle
title: Install, update and remove
apps: [luismc-docs, luismc-delivery]
topics: [delivery, docs, testing]
status: live
version: 0.3.2
owner: agents
type: explanation
code:
  - claude/plugins/docs/schemas/lifecycle.schema.json
  - claude/plugins/docs/templates/design-system/lifecycle/**
  - claude/plugins/docs/templates/design-system/parts/**
  - claude/plugins/docs/templates/design-system/guards/**
  - claude/plugins/delivery/templates/lifecycle/**
  - claude/plugins/delivery/templates/shared/scripts/delivery/lifecycle_*.py
last_verified: 2026-11-26
---
# Install, update and remove

## 1. In one paragraph

Every project with a local app (a service, a tray icon, a local console) installs, updates and removes it the same way, in its own look. A contract file in the design system, `lifecycle.json`, holds the states, words, defaults, paths and the systems the project ships for. Shared templates give the screens and the updater core. Checks LC-1 to LC-33 fail the build when a project leaves the contract. They run only for the systems the project ships for. A project may turn a check off only with a recorded owner decision.

## 2. Why

Each project built its own installer, updater, words and remove dialog, and each agent suggested something new. A study of three projects found three update engines, three retry rules, three remove dialogs and design-system rules for updates with no tests behind them. Notes did not stop the drift, so the standard is a contract with checks. The shared contract for the build is [lifecycle-contract](../../architecture/lifecycle-contract.md).

## 3. How it works

### Decisions (owner, 21 Nov 2026)

| ID | Decision |
|---|---|
| D-a | The OS package (msi, deb, rpm, pkg) is the update. The updater runs it silently. |
| D-b | Two policies: Automatic when idle (default, any idle time, optional time window) and Ask first. Required updates always install. |
| D-c | After a failed update test the old version runs again. Retry after 1 h, then 4 h; after the third failure, wait for a newer version. |
| D-d | A signed-in owner may start an install from any device. Every check, install, rollback and remove is audited with actor and result. |
| D-e | Remove asks every time with no default: Remove stays disabled until Keep my data or Delete my data too is chosen. A silent remove keeps data; `PURGE=1`, `apt purge` or `--delete-data` deletes it. |
| D-f | A signed manifest (Ed25519), SHA-256 and build provenance now. OS code signing per product by owner decision. |
| D-g | The web console comes first. One native window shows progress and questions. The tray only notifies. |
| D-h | Checks are on and block by default. An opt-out needs a decision ID, a reason and a review date. |
| D-i | Checks run only for the systems and distributions in the project's `targets`. Where test runs execute is the project's choice. |
| D-j | The design-system guards of DS234 block at once, with no warning period. |

### Open decisions

**O-1 — Where the result of a remove is kept.** After a successful remove the updater cannot write the result to its own history, because the product is gone. The owner has not chosen a rule. The options:

| Option | What keeps the record | Cost |
|---|---|---|
| A | The uninstaller writes one line to an OS log that stays after remove: Windows Event Log, journald or the unified log. | Three writers, one per OS. The log has its own retention, so the line can be rotated away. Reading it needs OS tools and rights. |
| B | A small remove-log file outside the product folders, kept after remove. | It is a leftover by definition: the leftover scan (LC-15, LC-33) needs an exception for it, and a purge must say whether it deletes it. One more path per OS. |
| C | The fleet or console server records it when the machine reports before the remove. | Records the intent, not the result. A machine that is offline, or that never reports, leaves no record. Needs a paired machine and a server. |

Until the owner decides, a remove writes no history entry and no check requires one.

### Parts

| Part | Plugin | What it does |
|---|---|---|
| `lifecycle.json` schema, starter and `words.json` | luismc-docs | The contract per project; words per state; banned words |
| UI part templates (React, Rust) | luismc-docs | Update banner, Updates card, history, remote update, remove dialog, fleet rows, native question window, tray model |
| Design-system guards | luismc-docs | Rendered layout and overlap, spacing tokens, layout roles, "none yet" limit, cited rule names its test, lifecycle UI guards |
| Updater test interface and conformance runner | luismc-delivery | A black-box run of the update flow against a fake signed update server |
| Updater core templates (Rust, Go) | luismc-delivery | State machine, manifest check, retry timer, policies, audit events |
| OS step scripts and lanes template | luismc-delivery | Install, upgrade, broken update, rollback, remove, purge and leftover scan per system |
| Release check and opt-out report | luismc-delivery | A release fails unless every target's lane passed; opt-outs listed with their cost |

### Flow

```mermaid
stateDiagram-v2
  direction LR
  [*] --> UpToDate
  UpToDate --> Available: check
  Available --> Waiting: Automatic when idle
  Available --> Review: Ask first
  Review --> Waiting: Update to version X
  Waiting --> Downloading: idle
  Downloading --> Verifying
  Verifying --> Refused: bad signature or hash
  Verifying --> Installing
  Installing --> Testing
  Testing --> Updated: self-test passes
  Testing --> RolledBack: fails
  RolledBack --> Available: retry 1 h, 4 h
  RolledBack --> Skipped: third failure
```

## 4. Requirements

**R1.1** — A project with a local app keeps `lifecycle.json` in its design system, valid against the schema (LC-1).

**R1.2** — Every lifecycle UI string comes from the words table and no banned word appears (LC-2, LC-31).

**R1.3** — The updater passes the conformance runner (LC-3 to LC-7, LC-25, LC-26, LC-28).

**R1.4** — Each target in `targets` passes its lane: install, upgrade, broken update and rollback, downgrade refused, remove, purge, leftover scan and package lints (LC-8 to LC-21, LC-29, LC-32, LC-33). LC-32 requires the artifact name `<Product>-<version>-<os>-<arch>.<ext>` per target. A system not in `targets` is not checked.

**R1.5** — The UI parts use the shared templates and tokens only and render without overlap or clipping (LC-22 to LC-24, LC-30).

**R1.6** — An opt-out names an owner decision, a reason and a review date; past the date the check fails again (LC-27).

## 5. Tests

| Requirement | Test |
|---|---|
| R1.1, R1.2 | `claude/plugins/docs/tests/test_ds235a_lifecycle_contract.py` |
| R1.3 | `claude/plugins/delivery/tests/test_ds235c_conformance.py` |
| R1.4 | `claude/plugins/delivery/tests/test_ds235d_os_steps.py`, `claude/plugins/delivery/tests/test_ds235d_release_optout.py` |
| R1.5 | `claude/plugins/docs/tests/test_ds235b_guards.py`, `claude/plugins/docs/tests/test_ds235b_parts.py` |
| R1.6 | `claude/plugins/delivery/tests/test_ds235d_release_optout.py` |

## Versions

Written by the release fold. Do not edit by hand.

| Version | Date | Release | What changed | Tasks |
|---|---|---|---|---|
| 0.3.2 | 2026-11-25 | RELEASE-182 | The design-system wizard guard kit gains the step-bar-more-for-one rule (specified in the docs feature, R5.25). | DS244 |
| 0.3.1 | 2026-11-22 | RELEASE-165 | Workflow templates read the per-job variable CRSP_<JOB> first (DL399). | DL399 |
| 0.3.0 | 2026-11-22 | RELEASE-163 | Adds the lifecycle adoption guide (retire no-timer tests, verify needs list, VM runner and opt-out) and records the removal-history decision as open (O-1). | DL393 |
| 0.2.0 | 2026-11-21 | RELEASE-161 | Release assets are named <Product>-<version>-<os>-<arch>.<ext>; the release check requires it per target (DL-96, LC-32). Updaters look for the new name first and the older name second for one transition release. | DL385 |

Written by the release fold. Do not edit by hand.
