---
title: Lifecycle contract
status: draft
---

# Lifecycle contract (DS235)

Shared contract for the install, update and remove standard. Four tasks build against it: DS235a (contract, words, words lint), DS235b (UI parts and design-system guards), DS235c (updater conformance kit), DS235d (OS test steps, release check, opt-out). Change this file only on the integration branch.

## Files

| File | Owner | Plugin |
|---|---|---|
| `claude/plugins/docs/schemas/lifecycle.schema.json` | DS235a | luismc-docs |
| `claude/plugins/docs/templates/design-system/lifecycle/` (starter `lifecycle.json`, `words.json`) | DS235a | luismc-docs |
| `claude/plugins/docs/templates/design-system/parts/` | DS235b | luismc-docs |
| `claude/plugins/docs/templates/design-system/guards/` | DS235b (DS235a adds the words-lint guard files only) | luismc-docs |
| `claude/plugins/delivery/templates/lifecycle/` (rust, go, test interface) | DS235c | luismc-delivery |
| `claude/plugins/delivery/templates/lifecycle/os/` | DS235d | luismc-delivery |
| `claude/plugins/delivery/templates/shared/scripts/delivery/lifecycle_conformance.py` | DS235c | luismc-delivery |
| `claude/plugins/delivery/templates/shared/scripts/delivery/lifecycle_release_check.py`, `lifecycle_optout.py` | DS235d | luismc-delivery |

## Project file

A project with a local app keeps `docs/design-system/vN/lifecycle.json`. Top-level keys: `schema` (`"1"`), `product`, `targets`, `paths`, `flows`, `defaults`, `words` (the words table, with project additions), `keep_on_remove`, `test_interface`.

`targets`: a list of `{ "os": "windows"|"linux"|"macos", "distro": "ubuntu-lts"|"fedora"|"debian"|null, "arch": "x64"|"arm64", "package": "msi"|"deb"|"rpm"|"pkg"|"tar" }`. Only targets the project releases for. The release check requires a passing lane per target.

## States

Install flow: `install`, `started`, `setup`, `ready`, `install_failed`.

Update flow: `unpaired`, `up_to_date`, `available`, `review`, `waiting`, `downloading`, `verifying`, `refused`, `installing`, `testing`, `updated`, `rolling_back`, `rolled_back`, `skipped`. No update check runs in `unpaired`.

Remove flow: `remove`, `ask`, `keep`, `purge`, `clean`.

## Decisions (owner, 21 Nov 2026)

- The OS package is the update; the updater runs it silently.
- Policies: `automatic_when_idle` (default, any idle time, optional time window) and `ask_first`. Required updates always install.
- Retry after a rollback: 1 h, then 4 h; after the third failure the version is skipped until a newer one.
- A signed-in owner may start an install from any device. Every check, install, rollback and remove is audited with actor and result.
- Remove asks every time with no default; Remove stays disabled until keep or delete is chosen. Silent remove keeps data; `PURGE=1`, `apt purge` or `--delete-data` deletes it.
- Trust: Ed25519-signed manifest, SHA-256 and build provenance; OS code signing per product by owner decision.
- Web first; one native window for progress and questions; the tray only notifies.
- Checks are on by default; an opt-out needs an owner decision ID, a reason and a review date.
- Where test runs execute is the project's choice.

## Defaults

Check every 6 h ± 20%, first check 1-10 min after start; failed-check backoff 1 min, 5 min, 30 min, 2 h. Self-test limit 180 s, poll 2 s; it opens the program's own stores that exist, never optional data. Wait for running work up to 60 min. Channel stable. Console on 127.0.0.1. Telemetry off.

## Check IDs

DS235a: LC-1, 2, 31. DS235b: LC-22, 23, 24, 30 and the design-system guards A-E (DS234). DS235c: LC-3 to 7, 25, 26, 28. DS235d: LC-8 to 21, 27, 29, 32, 33.
