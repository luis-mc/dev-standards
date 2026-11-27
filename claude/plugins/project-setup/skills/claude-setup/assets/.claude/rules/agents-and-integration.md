## Agents
- Orchestrator (strongest model): plan, write contracts, decide, review risky diffs. Never do mechanical work. <!-- advice -->
- Code agents: Sonnet at {{SUBAGENT_EFFORT}} effort; pass `effort: "{{SUBAGENT_EFFORT}}"` on every implementation Agent call (code, bug fixes, migrations, tests). <!-- check: DL-37 -->
- Opus agents (`model: "opus"`) and Sonnet agents both pass `effort: "medium"` unless the user chose otherwise in claude-setup. Use Opus after one failed Sonnet try (its test fails or it reports NOT READY; medium, then high; never Sonnet at xhigh), and for architecture, ambiguous specs, PR and security review (`luismc-agents:architect`). Hard root causes and cross-file refactors: the main session on Opus by `/model`. <!-- check: DL-37 -->
- Merges and checks: scripts. Conflicts a script cannot resolve: one Sonnet agent. Log triage: `model: "haiku"`. Lookups and read-only search: the Explore agent (Haiku); never Haiku for edits or judgment. <!-- advice -->
- Agents whose definition pins a model or effort keep it. <!-- advice -->
- Trivial edits (a typo, a one-line value) and tasks of about 3 tool calls or less: do them directly, because a subagent starts with a fresh context. <!-- advice -->
- Group tasks into one agent when they share files, a module, or one reads what the other wrote; brief it with all its tasks in order. Split only when the files are disjoint and the work can run in parallel, or one agent would pass about 5 tasks or half its context. Each extra agent re-reads the same files. <!-- advice -->
- Max 50 cloud agents at once (cap in `.delivery/config.json`), and at most 3 local agents, which run their tests on this machine. Split by file ownership; give overlapping work to one agent. <!-- check: DL-38, DL-41 -->
- Agents test only what they touch. A light change (docs, specs, config, small scripts: suites that finish in a few minutes locally) runs the touched suites locally. A heavy change (suites that take longer locally) runs a 1-2 minute local smoke of the touched suites, then CI on its branch for its area only (`gh workflow run <workflow> --ref <branch>`, with the workflow's area input where it has one), watched with `scripts/delivery/ci_watch.py`; that run replaces its local full run. Never the mutation pass locally (`--no-mutants` where supported), no local Docker unless a failure only reproduces there, and the full suite at most once, only when the change trips a full-run valve such as a lockfile or shared config. The ready PR's CI is the one full run. <!-- check: DL-12 -->
- Agents stop only processes and containers they started themselves; never kill by name or stop every container. <!-- check: DL-42 -->
- Agents write their report first, push after every step, and keep the report current. <!-- check: DL-44 -->
- Commit shared contracts to the integration branch before launching agents. <!-- check: DL-45 -->
- Run work in the cloud first; a local agent needs a `PC-bound:` reason line in its prompt unless the cloud cap is full. <!-- check: DL-39 -->
- Never send email, messages, posts, issues, comments or reviews in the owner's name; write drafts as files. On repositories the owner owns, agents may open pull requests, mark them ready and edit their title and description; merging stays the owner's. <!-- check: DL-73 -->
- No Co-Authored-By or AI attribution in commits or PR bodies when `.delivery/config.json` sets `no_attribution`. <!-- check: DL-74 -->

## Integrate once, deploy once
- Each change: own branch named `<task-id>-<slug>`, draft PR, branch gate in the agent sandbox (no Actions). <!-- check: DL-08 -->
- Open one ready PR when the join is pushed; its CI is the only full suite. Merge on green, never auto-merge. <!-- check: DL-05, DL-06, DL-08 -->
- Watch CI by the workflow runs for the head commit (`scripts/delivery/ci_watch.py`), never by the PR check list. <!-- check: DL-07 -->
- One deploy per merge; smoke-test production; fix forward on a new branch. <!-- check: DL-18 -->
- Details (CI-gate path, join, CI scope, watching CI, cleanup, artifacts, tools): read `docs/guides/agent-delivery-details.md` when you join, run CI or clean up. <!-- advice -->

## Docs
- Create every doc under `docs/`. <!-- check: DL-75 -->
