# Agent brief template

Copy, fill the `<...>`, and send it as the agent's prompt. The `delivery` block is read by the hooks (DL-30, DL-36, DL-37); its `docs:` line names the docs the task updates in the same branch (DOCSPEC R8.5, luismc-docs): the agent writes them, and a task that changes no docs says `none, <reason>` (the same reason goes in a `Docs: none, <reason>` commit line). Briefs and reports are temporary (R10.1): the join strips them, so keep anything worth keeping in a lasting doc; the markers below are what `brief_markers` in `.delivery/config.json` require. Replace the project's shared brief name (`BRIEF.md`) with the one it has.

````
This prompt is your BRIEF.md (<no-attribution line if the project sets no_attribution>). No push notifications. CRITICAL RUN RULE: never end your turn while waiting; push after every step; write your report first and keep it current.

```delivery
task: <task-id>
branch: <task-id>-<slug>
where: cloud
model: <model>
effort: medium
owns: <files or folders this agent alone changes>
docs: <the docs this task updates (paths under docs/), or "none, <reason>">
eta: setup <m> + work <m> + checks <m> = <total> min
```

<What to build, the files, the constraints.>

Your gate (pick the path your project uses):

A. Branch gate (default): run ONE affected gate at the end, one affected gate = `<the project's branch gate command>`; push only when it passes.

B. CI gate (a project with `scripts/delivery/agent_ci.py`): CI is the gate. Run only the tests of what you touch and the fast guards (`scripts/delivery/fast_guards.py`), never the full local gate, no mutation pass, no Docker. Push, then write a line `CODE DONE` in your report (`docs/agents/reports/<task-id>.md`) and push it. The branch CI run that `agent_ci.py` starts for that head is your gate; the orchestrator reads its result.

Report: what changed, what you ran, the branch head, last line READY or NOT READY: <why>.
````

Notes for the orchestrator on path B: size the ETA from coding time plus the branch CI run (state both parts in `eta:`); join urgent work at code push with `join.py --ci-gate`; the ready PR's CI is the full suite by inputs.
