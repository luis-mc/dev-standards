# Agent delivery details

The rules a project reads in every session are in `.claude/rules/agents-and-integration.md`. This guide holds the rest: read it when you join work, run CI, clean up or brief an agent that needs an outside site. Each line names what enforces it.

## Agents and the CI-gate path
- CI-gate path (only in a project that has `scripts/delivery/agent_ci.py`): an agent does not run the full local gate. It runs the tests of what it touched and the fast guards, pushes, and writes a `CODE DONE` line in its report; `scripts/delivery/agent_ci.py` then starts one CI run on that branch head, and that run is the agent's gate. <!-- check: DL-81, DL-12 -->
- On the CI-gate path a CI run started by hand plans what the branch brings since the default branch (`origin/<default>...HEAD`), never the last commit. A CI plan script that a helper imports has no top-level `await` (it deadlocks). <!-- check: DL-81, DL-83 -->
- Before briefing an agent that needs an external site, run `scripts/delivery/reach_check.py` in its sandbox; if it fails, fetch the material locally and commit it. <!-- check: DL-43 -->
- Worktrees and scratch live under the configured work root, never under the projects folder; remove them when done. <!-- check: DL-53 -->

## Integrate once, deploy once
- Trust an agent branch's gate only via `gate-result.json` matching the current head and base (`scripts/delivery/gate_verify.py`); the join checks it per branch, and no gate result is needed for the joined head or the ready PR. <!-- check: DL-13 -->
- The branch gate runs the always-on guards first, then typecheck + lint of the touched packages and their dependents, then unit / integration / e2e; a time-limited run always covers lint and types, and the pre-push hook runs them too. <!-- check: DL-84 -->
- A join is light: `scripts/delivery/join.py` merges the branches, resolves conflicts, folds spec notes, then checks typecheck and lint of what the merges touched and the fast guards; push and open the ready PR at once. Never run the branch gate or a full suite on the joined head, wait for a sandbox gate before the ready PR, or re-gate after a join fix. <!-- check: DL-11 -->
- On the CI-gate path the orchestrator joins urgent work at code push (a light join, `scripts/delivery/join.py --ci-gate`, no gate result needed) and sizes each ETA from coding time plus the branch CI run, not from a padded local gate. <!-- check: DL-83, DL-30 -->
- CI scope (`scripts/delivery/ci_scope.py`, patterns in `scripts/delivery/ci-scope.json`): a release PR runs the full suite; a change of CI files only runs the CI tests and the named smoke set; root configuration or the lockfile runs the full suite; everything else runs what it affects. Each run reports its time as the artifact `ci-run-times`. <!-- check: DL-80, DL-82 -->

## Watching CI and its guardrails
- Never `gh run watch` without `--interval 60` or more: the default 3 s drains the GitHub quota every session shares. Watch CI with `ci_watch.py`, one watcher for many runs (`ci_watch.py SHA1 SHA2 --run ID`). <!-- check: DL-95 -->
- A red release CI run finishes: never cancel it while jobs still run; wait, fix every failure, push once. Only a failure that blocks all later jobs (setup, lockfile, build) may be cancelled, with `# D105: blocks-all`. <!-- check: DL-97 -->
- No fail-fast on release PR CI: every matrix sets `fail-fast: false` and no suite stops at its first failure (`ci.jobs.<id>.fail_fast`). The sandbox branch gate keeps its cheapest-first stop. <!-- check: DL-98 -->
- Tests keep guardrails G1-G7: per-test timeout (unit 10 s, integration 60 s, e2e 2 min), job timeout-minutes ≤ 30, no CI retries, no sleeps, ≤ 20 cases per test, mutation off PR CI, test times reported. <!-- check: DL-99 -->

## Releases, deploys and cleanup
- A release leaves when its tasks are green; late branches ride the next release. <!-- check: DL-01, DL-16 -->
- No preview deploys for agent branches. Never merge mid-round to "see it deployed". <!-- check: DL-19 -->
- Never `vercel env rm` to narrow targets; after an env change re-list Production. <!-- check: DL-20 -->
- A gate that fails at `setup` means a stale lockfile (regenerate and commit it) or an install killed for memory (exit 137: larger pool cap or fewer parallel jobs). Never install unfrozen. <!-- check: DL-23 -->
- After the ready PR merges, run `scripts/delivery/cleanup.py --pr <N>`: it removes the release's branches, gate-result refs and worktrees. Leave nothing behind. <!-- check: DL-14 -->
- Build artifacts on GitHub (installers such as MSI, bundles, reports): keep only the newest of each name. Give each kind a stable name; `artifact-prune.yml` deletes the older ones once a day. <!-- check: DL-22 -->
- CI jobs fetch pinned tools through `scripts/delivery/ci_tool.py`: a per-runner cache, sha256-checked, with retries; never a bare download into RUNNER_TEMP. <!-- check: DL-94 -->
