## Agents
- Orchestrator (strongest model): plan, write contracts, decide, review risky diffs. Never do mechanical work.
- Code agents: Sonnet at {{SUBAGENT_EFFORT}} effort; pass `effort: "{{SUBAGENT_EFFORT}}"` on every implementation Agent call.
- Opus agents (`model: "opus"`) and Sonnet agents both pass `effort: "medium"` unless the user chose otherwise in claude-setup.
- Merges and checks: scripts. Conflicts a script cannot resolve: one Sonnet agent. Log triage: `model: "haiku"`.
- Agents whose definition pins a model or effort keep it.
- Trivial edits (a typo, a one-line value): do them directly.
- Max 5 agents at once, and at most 3 when they run heavy test suites on the same machine. Split by file ownership; give overlapping UI work to one agent.
- Agents test only what they touch. A light change (docs, specs, config, small scripts: suites that finish in a few minutes locally) runs the touched suites locally. A heavy change (suites that take longer locally) runs a 1-2 minute local smoke of the touched suites, then CI on its branch for its area only (`gh workflow run <workflow> --ref <branch>`, with the workflow's area input where it has one), watched with `scripts/delivery/ci_watch.py`; that run replaces its local full run. Never the mutation pass locally (`--no-mutants` where supported), no local Docker unless a failure only reproduces there, and the full suite at most once, only when the change trips a full-run valve such as a lockfile or shared config. The ready PR's CI is the one full run.
- Agents stop only processes and containers they started themselves; never kill by name or stop every container.
- Agents write their report first, push after every step, and keep the report current.
- Commit shared contracts to the integration branch before launching agents.
- Before briefing an agent that needs an external site, run `scripts/delivery/reach_check.py` in its sandbox; if it fails, fetch the material locally and commit it.

## Integrate once, deploy once
- Each change: own branch named `<task-id>-<slug>`, draft PR, branch gate in the agent sandbox (no Actions).
- Trust a gate only via `gate-result.json` matching the current head and base (`scripts/delivery/gate_verify.py`).
- Join with `scripts/delivery/join.py`; it runs the branch gate on the joined head, unless that tree equals a branch head whose gate result it already trusts.
- Open one ready PR when the join is pushed; its CI is the only full suite. Merge on green, never auto-merge.
- Watch CI by the workflow runs for the head commit (`scripts/delivery/ci_watch.py`), never by the PR check list.
- A train leaves when its cargo is green; late branches ride the next train.
- One deploy per merge; smoke-test production; fix forward on a new branch.
- No preview deploys for agent branches. Never merge mid-round to "see it deployed".
- A gate that fails at `setup` means a stale lockfile: regenerate and commit it, never install unfrozen.
- After the ready PR merges, run `scripts/delivery/cleanup.py --pr <N>`: it removes the train's branches, gate-result refs and worktrees. Leave nothing behind.
- Build artifacts on GitHub (installers such as MSI, bundles, reports): keep only the newest of each name. Give each kind a stable name; `artifact-prune.yml` deletes the older ones after every run.

## Docs
- Create every doc under `docs/`.
