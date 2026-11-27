---
title: Testing in dev-standards
type: how-to
version: 0.1.1
last_verified: 2026-11-27
---
# Testing in dev-standards

The shipped agent test rule (DELIVERYSPEC DL-12: agents test only what they touch) applies here. The ready PR and the mutation passes differ from the shipped rules (see below). How the rule maps onto this repository:

- **Which case am I?** `python tools/ci_areas.py --branch-advice` reads the branch's diff against `origin/main` and prints `light: test locally only` or `heavy: <areas> -> run ...`.
- **Light** (the `specs` or `profiles` area: specs, skill text, rules): run the touched suites locally.
- **Heavy** (the `delivery` or `artifacts` area): a 1-2 minute local smoke (`-k <scenario>` of what you changed, `--no-mutants`). Then run branch CI for your own area only, with the one command the advice prints: `gh workflow run spec-lint.yml --ref <branch> -f areas=<areas>`. Watch it with `python claude/plugins/delivery/templates/shared/scripts/delivery/ci_watch.py <sha> --workflow spec-lint.yml`. This is the only way an agent starts branch CI here. Never run a full local pass of a heavy suite.
- **The ready PR** runs only the areas its diff touches. This repository deviates from DELIVERYSPEC DL-80, where a release PR runs everything on its first run; the [test-cost spec](../features/test-cost/spec.md) R5.2 says why. The mutation passes run only when the delivery scripts or their suites change (test-cost R5.3). `nightly.yml` runs every area with mutants on `main`.
- Suites, areas and the path map: `tools/ci_areas.py`. Measurements behind these choices: `docs/project/feature-test-and-validation-cost.html`.

**Plugin smoke.** dev-standards deploys nothing, so the `Plugin smoke` workflow (`.github/workflows/plugin-smoke.yml`, run on every push to `main`) is its DL-18 smoke. It runs `python tools/plugin_smoke.py`, which checks each plugin under `claude/plugins/`: the manifest, the hook scripts, that scripts compile and answer `--help`, and the skill front matter. `.delivery/config.json` names it in `smoke_workflow`.

**The docs-check job.** It waits for the `areas` job. `tools/ci_areas.py` sets its `docs_check` output when a change touches `docs/`, `AGENTS.md`, `CLAUDE.md`, `tools/`, `claude/` or `.github/workflows/`. A change only under `.claude/`, or a draft pull request, skips it. A push to main, a manual run of docs or specs, and an unreadable range run it.

## Versions

Written by the release fold. Do not edit by hand.

| Version | Date | Release | What changed | Tasks |
|---|---|---|---|---|
| 0.1.1 | 2026-11-27 | RELEASE-210 | The ready PR states this repository's deviation from DELIVERYSPEC DL-80 and cites test-cost R5.2. A heavy change runs a short local smoke, then branch CI for its own area by one named command. Front matter gets a title and type. | DS306 |
| 0.1.0 | 2026-11-25 | RELEASE-175 | spec-lint's docs-check job now waits for the areas job and runs only when a change touches docs/, AGENTS.md, tools/, claude/ or the workflows; tools/ci_areas.py emits a docs_check output. | DP5 |
