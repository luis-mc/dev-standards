## Agents
- Orchestrator (strongest model): plan, write contracts, decide, review risky diffs. Never do mechanical work.
- Code agents: Sonnet at {{SUBAGENT_EFFORT}} effort; pass `effort: "{{SUBAGENT_EFFORT}}"` on every implementation Agent call.
- Opus agents (`model: "opus"`) and Sonnet agents both pass `effort: "medium"` unless the user chose otherwise in claude-setup.
- Merges and checks: scripts. Conflicts a script cannot resolve: one Sonnet agent. Log triage: `model: "haiku"`.
- Agents whose definition pins a model or effort keep it.
- Trivial edits (a typo, a one-line value): do them directly.
- Max 5 agents at once, and at most 3 when they run heavy test suites on the same machine. Split by file ownership; give overlapping UI work to one agent.
- Agents test fast locally: suites without the mutation pass (`--no-mutants` where supported), no local Docker unless a failure only reproduces there. Mutation passes and Linux run in CI: the agent triggers the workflow on its branch (`gh workflow run <workflow> --ref <branch>`; drafts skip CI) and watches it with `scripts/delivery/ci_watch.py`.
- Agents write their report first, push after every step, and keep the report current.
- Commit shared contracts to the integration branch before launching agents.
- Before briefing an agent that needs an external site, run `scripts/delivery/reach_check.py` in its sandbox; if it fails, fetch the material locally and commit it.

## Integrate once, deploy once
- Each change: own branch named `<task-id>-<slug>`, draft PR, branch gate in the agent sandbox (no Actions).
- Trust a gate only via `gate-result.json` matching the current head and base (`scripts/delivery/gate_verify.py`).
- Join with `scripts/delivery/join.py`; it runs the branch gate on the joined head.
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
