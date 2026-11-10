# DL176 report

## Base check
`git fetch origin main && git checkout -B DL176-pool-resize-fix origin/main`, then `git merge-base --is-ancestor f3a205ee HEAD` succeeded (printed ANCESTOR_OK). Base: f3a205e.

## What changed
- `delivery_runner_pool.py`
  - `detect_host`: 5 memory samples, 1 s apart through `probe.sleep`; `used_gib` is the median. `used_samples` lists them.
  - `pick_browsers(..., current)`: keeps the `.env` value; detection only raises none to chromium.
  - `plan()`: keeps `PLAYWRIGHT_VERSION`, `POOL_LAYERS`, `POOL_APT`, `POOL_LAYER_SOURCES` from the `.env`; takes `drop_layers`, `drop_apt`.
  - `write_pool_files` keeps every other `.env` line (it used to drop layers and apt).
  - `keep_owner_cap(..., shrink)`: a `--resize` that lowers POOL_MEM or POOL_CPUS refuses without `--shrink`.
  - New `owner_target` and `resolve_cap`: `--pool-gib` / `--pool-cpus`, checked against the 85% memory budget, 60% CPU budget, floors and 1.5 GiB per CPU. The refusal names the short budget.
  - `measured_sizing` also returns budget, room and sample count.
- `delivery_ci_setup.py`: pool-plan and pool-run pass `--browsers`, `--playwright`, `--drop-layer`, `--drop-apt`, `--shrink`, `--pool-gib`, `--pool-cpus`; help text for `--cpus` and `--used-gib` now says machine numbers; the plan prints a "Sizing inputs" line.
- Docs: runner-pool spec R5.19 to R5.21, feature note `docs/features/runner-pool/changes/DL176.md`, change note `docs/architecture/changes/DL176-pool-resize.md`.
- Outside my list (needs a look): `tests/test_dl103_pool_keep_cap.py` had one test that expects `--resize` to lower the cap; it now passes `shrink=True`. The delivery spec is untouched; the commit message says `Docs: none` for it (M1).
- Not done: the skill text under `skills/delivery-ci-setup/` was not changed (no resize text there needed edits).

## Plan text for the case above
31.7 GiB, 20 CPUs, VM 11 GB, .env 8.5g / 4.0 / chromium / windows-packaging, `--pool-gib 12 --pool-cpus 8` (8 GiB used outside WSL in the fake probe):

```
Plan (nothing has changed yet):
Found: 3 repositories you administer, 1 runner services, 1 runner folders, 2 containers.
  owner/locked: runners not readable (gh refused (admin rights needed?))
Pool cap: 12 GiB memory, 8 CPUs (measured on this machine unless you gave a number).
  Sizing inputs: total 31.7 GiB; used outside WSL 8.0 GiB (median of 5 samples); 85% budget 26.9 GiB; room 18.9 GiB; Docker ceiling 11.0 GiB.
  Cap changed: the pool size you gave (12 GiB, 8 CPUs) replaces the cap in .env.
  - Wait until no existing runner has a job [I run it]
  - Remove runner host1-old (Windows) from owner/example-app [asks a second yes (deletes)]
  - Delete the old runner folder C:/Work/runners/app1 [asks a second yes (deletes)]
  - Stop and delete the container old-runner [asks a second yes (deletes)]
  - Write the machine config (limits, slots) through the machine layer [I run it]
  - Write C:/Users/u1/.wslconfig with the pool ceiling (memory 11GB -> 14GB, processors 5 -> 9; the old file is kept as .bak) [I run it]
  - Restart WSL so the ceiling applies (only when no job runs; stops every container) [I run it]
  - Write the pool files for "main" (compose, agents.json, .env: POOL_MEM 8.5g -> 12g, POOL_CPUS 4.0 -> 8, POOL_CPUSET, POOL_CPUS_INT, POOL_BROWSERS chromium). The image includes the Chromium system libraries and is larger (about 300-400 MB). Jobs install the browser itself with `playwright install chromium`. Playwright 1.60.0 (kept from the pool .env). Layers kept: windows-packaging. Apt packages kept: jq. size set by --pool-gib/--pool-cpus (measured now: 8.5 GiB, 4.0 CPUs). [I run it]
  - Build and start the pool container [I run it]
  - Add one pool agent for owner/example-app [already set]
  - Set CI_RUNS_ON for owner/example-app [I run it]
  - Verify: each agent online with its labels, then one pool-check run per repository [I run it]
Writes in this repository: nothing. Writes on this machine: /tmp/dl-iso-p07gm6cw/machine/pools/main
Changes outside the repository: GitHub runner registrations, repository variables, Docker, the machine config.
Needs you: a yes for each step; a yes that names what is deleted.
About 38 minutes.
```

Result: POOL_MEM 8.5g -> 12g, POOL_CPUS 4.0 -> 8, .wslconfig memory 11GB -> 14GB (pool 12 + sidecar 1 + VM headroom 1), processors 5 -> 9; chromium and windows-packaging kept.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl176_pool_resize`: 23 tests, OK.
- `python3 -m unittest test_runner_pool test_dl101_pool_browsers test_dl103_pool_keep_cap test_dl92_pool_fixes test_dl149_pool_layers test_ci_setup test_dl155_pool_refresh_shared test_dl162_pool_refresh_files`: 263 tests, OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only G1 (decisions.md stale, also on main) and W1 (this report under docs/work/) as errors.
- `spec-lint.yml` on the branch, run 42859834913 (head 876c4a8), all jobs ended:
  - success: which areas, delivery CI scripts and workflow templates, setup preflight, artifact pruning, branch gate and trust rule, area mapping, runner plan, docs plugin, plugin ledger/recorder/watcher/hooks, packaged-program smoke test, change notes enforced and folded, train cleanup, delivery scripts/CI templates/cleanup/prune/change notes (summary).
  - failure: docs check (G1 and W1 only, same as local).
  - skipped: change notes, change notes folded, branch gate shard, specs/templates/AUTHSPEC, transcript folds, model profiles, artifact renderer.
- No mutation passes, no Docker.

## Branch head
See the git log of DL176-pool-resize-fix; code head tested in CI: 876c4a84d539d965c3e4cb8811879283f45fcb52.

READY
