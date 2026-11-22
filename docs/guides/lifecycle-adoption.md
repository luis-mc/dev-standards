---
title: Adopt the lifecycle kit in a project
type: how-to
---
# Adopt the lifecycle kit in a project

Use this guide when a project with a local app takes the lifecycle kit (templates, checks LC-1 to LC-33). The rules are in the [lifecycle spec](../features/lifecycle/spec.md). The updater contract is in `claude/plugins/delivery/templates/lifecycle/CONTRACT.md`. These notes come from a project that adopted the kit.

## 1. Retire tests that say the updater has no timer

An older project may hold tests that assert the updater runs no timer, or makes no request on its own. They conflict with LC-5: the first check is 60 to 600 s after start, then one check every 6 h ± 20%.

1. Find them: search the tests for "no timer", "no background check" and "never checks on its own".
2. Delete them in the same change that adds the updater core. Do not skip or loosen them.
3. The conformance runner covers the timer now (LC-5). LC-28 keeps its one limit: no check while unpaired.

## 2. Add `lifecycle-check` to `verify`

When you add `lifecycle-check` to the `needs` list of the verify job, a project test that pins that list fails. Update the pinned list in the same change. A change that adds the job and leaves the test red is not done.

## 3. VM runner

Lifecycle lanes install and remove the product and scan for leftovers. A lane needs a disposable Windows machine. A developer PC that has the products installed is refused: it hides leftovers and a failed remove can break it.

Set it up:

1. Pick a runner. Either a fresh Windows VM that you reset before each run, or a GitHub-hosted runner: `windows-latest` (x64) or `windows-11-arm` (arm64).
2. A VM is reset per run: restore a clean snapshot, or build a new one from the base image. Never reuse a machine that ran a lane.
3. Register the runner with the repository or the pool. A self-hosted VM takes a label, for example `lifecycle-windows`.
4. Set the repository variable `LIFECYCLE_RUNS_ON_WINDOWS` to the JSON value of `runs-on`, for example `["windows-latest"]` or `["self-hosted","lifecycle-windows"]`. The template `os/lifecycle-lanes.yml` skips a lane with no variable.
5. Run the lane once from `workflow_dispatch`. Check that `lifecycle-result-windows.json` is uploaded.

Until the runner exists, record an opt-out in `.delivery/config.json` under `lifecycle.off`, for each check the lane would run (LC-27, R1.6):

```json
{ "lifecycle": { "off": { "LC-9": { "decision": "D-123", "reason": "no disposable Windows runner yet", "review": "2026-12-31" } } } }
```

It needs a decision ID, a reason and a review date. Past the date the check fails again. `python scripts/delivery/lifecycle_optout.py check` lists what each opt-out costs. Remove the opt-outs when the runner is registered.
