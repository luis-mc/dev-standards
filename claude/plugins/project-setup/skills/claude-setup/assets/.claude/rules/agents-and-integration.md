## Agents
- Orchestrator (strongest model): plan, write contracts, decide, review risky diffs. Never do mechanical work. <!-- advice -->
- Code agents: Sonnet at {{SUBAGENT_EFFORT}} effort; pass `effort: "{{SUBAGENT_EFFORT}}"` on every implementation Agent call. <!-- check: DL-37 -->
- Opus agents (`model: "opus"`) and Sonnet agents both pass `effort: "medium"` unless the user chose otherwise in claude-setup. <!-- check: DL-37 -->
- Merges and checks: scripts. Conflicts a script cannot resolve: one Sonnet agent. Log triage: `model: "haiku"`. <!-- advice -->
- Agents whose definition pins a model or effort keep it. <!-- advice -->
- Trivial edits (a typo, a one-line value): do them directly. <!-- advice -->
- Max 50 cloud agents at once (cap in `.delivery/config.json`), and at most 3 local agents, which run their tests on this machine. Split by file ownership; give overlapping UI work to one agent. <!-- check: DL-38, DL-41 -->
- Agents test only what they touch. A light change (docs, specs, config, small scripts: suites that finish in a few minutes locally) runs the touched suites locally. A heavy change (suites that take longer locally) runs a 1-2 minute local smoke of the touched suites, then CI on its branch for its area only (`gh workflow run <workflow> --ref <branch>`, with the workflow's area input where it has one), watched with `scripts/delivery/ci_watch.py`; that run replaces its local full run. Never the mutation pass locally (`--no-mutants` where supported), no local Docker unless a failure only reproduces there, and the full suite at most once, only when the change trips a full-run valve such as a lockfile or shared config. The ready PR's CI is the one full run. <!-- check: DL-12 -->
- CI-gate path (only in a project that has `scripts/delivery/agent_ci.py`): an agent does not run the full local gate. It runs the tests of what it touched and the fast guards, pushes, and writes a `CODE DONE` line in its report; `scripts/delivery/agent_ci.py` then starts one CI run on that branch head, and that run is the agent's gate. <!-- check: DL-81, DL-12 -->
- On the CI-gate path a CI run started by hand plans what the branch brings since the default branch (`origin/<default>...HEAD`), never the last commit. A CI plan script that a helper imports has no top-level `await` (it deadlocks). <!-- check: DL-81, DL-83 -->
- Agents stop only processes and containers they started themselves; never kill by name or stop every container. <!-- check: DL-42 -->
- Agents write their report first, push after every step, and keep the report current. <!-- check: DL-44 -->
- Commit shared contracts to the integration branch before launching agents. <!-- check: DL-45 -->
- Before briefing an agent that needs an external site, run `scripts/delivery/reach_check.py` in its sandbox; if it fails, fetch the material locally and commit it. <!-- check: DL-43 -->
- Run work in the cloud first; a local agent needs a `PC-bound:` reason line in its prompt unless the cloud cap is full. <!-- check: DL-39 -->
- Worktrees and scratch live under the configured work root, never under the projects folder; remove them when done. <!-- check: DL-53 -->
- Never send email, messages, posts, issues or comments in the owner's name; write drafts as files. <!-- check: DL-73 -->
- No Co-Authored-By or AI attribution in commits or PR bodies when `.delivery/config.json` sets `no_attribution`. <!-- check: DL-74 -->

## Integrate once, deploy once
- Each change: own branch named `<task-id>-<slug>`, draft PR, branch gate in the agent sandbox (no Actions). <!-- check: DL-08 -->
- Trust an agent branch's gate only via `gate-result.json` matching the current head and base (`scripts/delivery/gate_verify.py`); the join checks it per branch, and no gate result is needed for the joined head or the ready PR. <!-- check: DL-13 -->
- The branch gate runs the always-on guards first, then typecheck + lint of the touched packages and their dependents, then unit / integration / e2e; a time-limited run always covers lint and types, and the pre-push hook runs them too. <!-- check: DL-84 -->
- A join is light: `scripts/delivery/join.py` merges the branches, resolves conflicts, folds spec notes, then checks typecheck and lint of what the merges touched and the fast guards; push and open the ready PR at once. Never run the branch gate or a full suite on the joined head, wait for a sandbox gate before the ready PR, or re-gate after a join fix. <!-- check: DL-11 -->
- On the CI-gate path the orchestrator joins urgent work at code push (a light join, `scripts/delivery/join.py --ci-gate`, no gate result needed) and sizes each ETA from coding time plus the branch CI run, not from a padded local gate. <!-- check: DL-83, DL-30 -->
- CI scope (`scripts/delivery/ci_scope.py`, patterns in `scripts/delivery/ci-scope.json`): a release PR runs the full suite; a change of CI files only runs the CI tests and the named smoke set; root configuration or the lockfile runs the full suite; everything else runs what it affects. Each run reports its time as the artifact `ci-run-times`. <!-- check: DL-80, DL-82 -->
- Open one ready PR when the join is pushed; its CI is the only full suite. Merge on green, never auto-merge. <!-- check: DL-05, DL-06, DL-08 -->
- Watch CI by the workflow runs for the head commit (`scripts/delivery/ci_watch.py`), never by the PR check list. <!-- check: DL-07 -->
- A train leaves when its cargo is green; late branches ride the next train. <!-- check: DL-01, DL-16 -->
- One deploy per merge; smoke-test production; fix forward on a new branch. <!-- check: DL-18 -->
- No preview deploys for agent branches. Never merge mid-round to "see it deployed". <!-- check: DL-19 -->
- Never `vercel env rm` to narrow targets; after an env change re-list Production. <!-- check: DL-20 -->
- A gate that fails at `setup` means a stale lockfile: regenerate and commit it, never install unfrozen. <!-- check: DL-23 -->
- After the ready PR merges, run `scripts/delivery/cleanup.py --pr <N>`: it removes the train's branches, gate-result refs and worktrees. Leave nothing behind. <!-- check: DL-14 -->
- Build artifacts on GitHub (installers such as MSI, bundles, reports): keep only the newest of each name. Give each kind a stable name; `artifact-prune.yml` deletes the older ones after every run. <!-- check: DL-22 -->

## Docs
- Create every doc under `docs/`. <!-- check: DL-75 -->
