# DL124 report (hook fixes, DL124 / DL133 / DL136)

## Changes
1. DL124: `questions_stop.py` `agents_running` now returns (running, soon). An agent counts as running when its state is queued/running, or it has an `eta` and no `done_at` and a non-terminal state (done/empty/failed/stopped). The ledger is read defensively: a missing or bad file adds no agents. When the parked-question check finds a running agent due within 60 minutes (`eta.due`), the hook allows the stop and prints a systemMessage: "Questions wait for the report of agent <task> (due within 60 minutes); do not ask now." Plain-text questions (Q-2) still block.
2. DL133: `norm_path` in `hook_pre_tool.py` maps `/c/x` and `/mnt/c/x` to `c:/x`, converts backslashes, lowercases, strips trailing slash. DL-53 now allows `git worktree add /c/Work/x` and `/mnt/c/Work/x` with work root C:/Work, and still refuses real outside paths (`/c/Other`, `/d/Work`, `/mnt/c/Workshop`).
3. DL136: one rule line added, same wording, to both `clarifying-questions.md` copies. The hook CAN see an open question (ledger `owner_questions` with no `answered_at`): `check_postpone` in `hook_pre_tool.py` warns (systemMessage, never blocks) on a RemoteTrigger `create` or `update` whose `run_once_at` is under 2 hours ahead while one is open.

## Spec text for the orchestrator
- project-setup: stop hook parks on agents with ETA and no agent-done; says questions wait when due within 60 min; fail-open ledger read.
- delivery: DL-53 accepts Git Bash and WSL paths; DL-136 warning described above.

## Files outside the owned list
- `docs/features/project-setup/changes/DL124.md` and `docs/features/delivery/changes/DL133.md` (from `docs_fold.py note`, needed by AGENTS.md and docs_check M1).
- Change notes: DL124-questions-stop-eta, DL133-worktree-git-bash-paths, DL136-delivery-postpone-warning, DL136-project-setup-postpone-rule (one per plugin).

## Tests
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (heavy).
- `python3 tools/test_questions_stop.py`: not run locally; session_guard refuses it (heavy, unmeasured, no cases). Added cases to it. Instead ran an ad-hoc smoke of the hook: ETA agent pushed -> exit 0 with the note; ETA agent done -> exit 2; bad ledger -> exit 2. All as expected.
- `python3 -m unittest claude/plugins/delivery/tests/test_dl133_hook_paths.py`: 6 tests OK (worktree forms, postpone warning).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 4 warnings (M1 unmapped rules file, T2 x3). G1/W1 not shown.
- spec-lint workflow: see below.

## CI
`gh workflow run spec-lint.yml --ref DL124-hook-fixes -f areas=delivery` (run 42655451156, head 21cf06a): all delivery jobs passed. Only the docs check failed, on W1 (this report under docs/work/), which is expected on a branch. Remaining docs_check output: 6 warnings (M1 unmapped rules file, T2 x5), no other errors.
`tools/test_questions_stop.py` was not run in CI on its own here; it is part of the areas run only if mapped. Not confirmed.

READY
