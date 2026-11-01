---
title: Performance audit of the plugin hooks and delivery scripts, 2026-11-01
type: explanation
---
# Performance audit of the plugin hooks and delivery scripts, 2026-11-01

Report only. No code, config or other doc was changed. The procedure is the `luismc-audits` performance-audit skill, scoped to the plugin hooks and scripts, which cost time on every tool call, turn end and session start.

## Summary

Most hooks are cheap: 33 to 55 ms, close to the 12 ms Python start-up. Three things are not fine:

1. The machine load guard sleeps 1 second to take a CPU sample, and it does so on every turn end and session start when the last sample is older than 10 seconds (it also sleeps on heavy Bash calls).
2. The delivery ledger only grows (except `events`), and each hook parses the whole file. At 20,000 rows a `PostToolUse` run takes 874 ms.
3. The `DL-76` check in the delivery Stop hook makes several `gh` calls per merged train on every turn end (opt-in, estimated).

### Hook timings

Median of 7 to 15 runs, wall clock, one process per run, fixture repo with `.delivery/`, `docs/docs.json` and an artifact record. Machine: 1 cloud container, `python3` start-up alone is 12 ms. "Calls" are `subprocess` calls counted with a wrapper (hook plus any child script it starts).

| Hook (entry point) | Event | Median ms | Subprocess calls | Notes |
|---|---|---|---|---|
| delivery `hook_pre_tool.py`, light Bash | PreToolUse | 44 | 0 | load sample not needed |
| delivery `hook_pre_tool.py`, heavy Bash, load cache warm | PreToolUse | 45 | 0 | |
| delivery `hook_pre_tool.py`, heavy Bash, load cache older than 10 s | PreToolUse | 1050 to 1100 | 0 (+1 `ps` only when refusing) | 1.0 s sleep |
| delivery `hook_post_tool.py`, `git push` / `ls` | PostToolUse | 49 / 50 | 0 | |
| delivery `hook_stop.py`, cache warm | Stop | 46 | 0 | |
| delivery `hook_stop.py`, cache older than 10 s | Stop | 1050 to 1070 | 0 | 1.0 s sleep |
| delivery `hook_session_start.py`, cache warm / cold | SessionStart | 42 / 1050 | 0 | |
| artifacts `hook_after_command.py` | PostToolUse | 33 to 35 | 1 (`git rev-parse`) | only if the command is classified |
| artifacts `hook_end_of_turn.py` | Stop | 172 | 6 (2 direct, 4 inside `pending`) | |
| artifacts `hook_session_start.py` | SessionStart | 211 | 7 (incl. 1 `gh pr list`) | `gh` failed fast here; real network cost not measured |
| docs `hook_stop.py` | Stop | 55 | 5 `git` | |
| docs `hook_session_start.py` | SessionStart | 44 | 0 | |
| artifacts `hook_before_command.py` | none | n/a | 0 | the script is an empty no-op and is not in `hooks.json` |

Per Bash call the three plugins add about 45 + 50 + 35 = 130 ms (if they run one after another; they may run in parallel). Per turn end the sum is about 46 + 172 + 55 = 275 ms warm, or about 1.3 s when the load cache is cold.

### Ledger growth (delivery hooks, fixture ledger)

Rows are split evenly over `trains`, `agents`, `publishes` and `owner_questions`.

| Rows per list | Ledger size | pre_tool ms | stop ms | post_tool ms |
|---|---|---|---|---|
| 0 | 0.2 KB | 44 | 42 | 49 |
| 500 | 0.45 MB | 50 | 52 | 73 |
| 5,000 | 4.6 MB | 91 | 120 | 239 |
| 20,000 | 18 MB | 183 | 378 | 874 |

## Findings, most severe first

Severity follows the skill rubric, read for a local hook: P1 is a visible, avoidable wait on a hot path; P2 is waste that grows; P3 has no current measurable cost.

### Finding 1: Load guard sleeps 1.0 s per fresh sample (P1, measured)

- **Location:** `claude/plugins/delivery/scripts/load.py:211` and `:222` (`time.sleep(seconds)`, `SAMPLE_SECONDS = 1.0` at `:31`, `CACHE_TTL = 10.0` at `:28`); callers `load_guard.py:219` (`notice`) and `:235` (`with_notice`), `hook_stop.py:485`, `hook_session_start.py:122`, and `load_guard.py` `check_call` for heavy tool calls.
- **Cost per call:** 1.05 s extra, measured 7 of 7 cold runs (1,045 to 1,097 ms against 42 to 49 ms warm). Same for Stop, SessionStart and heavy Bash calls spaced more than 10 s apart.
- **Scenario:** `with_notice` runs on every Stop and SessionStart in every project where the plugin is on, with or without `.delivery/`. A normal turn is longer than 10 s, so the cache is almost always stale at turn end. Every turn end pays one second of idle wait. A burst of heavy commands (test runs) pays it again once per 10 s.
- **Fix:** Take the CPU delta from the previous cached sample (the cache already keeps the last 3) instead of sleeping. Fall back to the 1 s sleep only when there is no sample younger than about 60 s. A second option: use `os.getloadavg()` on Linux and macOS, as the macOS path already does as a fallback.

### Finding 2: Delivery ledger rows never expire, and every hook reads all of them (P2, measured)

- **Location:** `claude/plugins/delivery/scripts/hooklib.py:155` (`load_ledger`, full `json.load` on every hook run); `delivery_ledger.py:37` and `:215` (`EVENT_CAP = 500` caps `events` only); `delivery_ledger.py:191-205` (`write_atomic`: `indent=2`, `fsync`, full rewrite).
- **Cost per call:** see the growth table. About 0.3 ms per 100 rows for reads. A write costs about 3 times a read. 874 ms per `PostToolUse` at 20,000 rows per list (18 MB).
- **Scenario:** `trains`, `agents`, `jobs`, `installs`, `publishes`, `runners`, `watchers` and `owner_questions` are only appended to. Nothing removes a merged train or a done agent. With 20 trains and 30 agent launches a week, this reaches 5,000 rows in roughly 2 to 3 years, so today it is small. It is a certain slow climb, not an emergency. Pre-tool and post-tool hooks run on every Bash call, so the cost is multiplied by the call count.
- **Fix:** Cap each list like `events` (keep all open rows, keep the last N terminal rows, for example 200), or move closed rows to `.delivery/ledger-archive.json`. Optionally drop `indent=2` and `fsync` on hook-side writes.

### Finding 3: `DL-76` check makes many sequential `gh` calls on every turn end (P2, estimated)

- **Location:** `claude/plugins/delivery/scripts/hook_stop.py:331-366` (`check_one_ci_per_release`), called at `:439`; `gh_json` at `:321` (timeout 25 s per call, hook timeout 60 s in `hooks.json`).
- **Cost per call:** not measured, `gh` has no network here. Per merged, not yet cleaned train: 1 `pr view` + 2 `api` + 1 `run list` + 1 `run view` per workflow run. A typical 5-run train is 9 `gh` calls, about 3 to 5 s at 300 to 500 ms each. Three such trains approach 15 s per turn end.
- **Scenario:** Active only when `pr_proven_jobs` is set. A train stays in the list until `cleanup.py` marks it terminal, so a forgotten train repeats the same 9 calls at every turn end for as long as it sits there. The answer for a given merge commit never changes.
- **Fix:** Cache the result per merge commit in the ledger (or `.delivery/state`), and skip trains already checked. Run the per-run `run view` calls only for runs whose workflow name matches. Cap the number of trains checked per turn.

### Finding 4: Artifacts Stop hook starts a second Python process that imports a 3,100-line module (P3, measured)

- **Location:** `claude/plugins/artifacts/scripts/hook_end_of_turn.py:45-50` (`pending_items` runs `project_artifacts.py pending --json`; `PENDING_TIMEOUT = 90` at `:35`).
- **Cost per call:** 172 ms total against about 35 ms for the other artifact hook. The child run is about 115 ms (cProfile: 4 `git` calls, 342 regex compiles, 9,540 `deepcopy` calls in `load`).
- **Scenario:** Every turn end in every project with an artifact record, even when nothing is pending (the common case). Not a large wait, but it is the second heaviest warm hook.
- **Fix:** Import `project_artifacts` in process (it is the same plugin) or read `manifest.json` and the queue file first and skip `pending` when the queue is empty and no artifact is marked dirty. Avoid `deepcopy` in `load` for a read-only call.

### Finding 5: Artifacts SessionStart makes a network `gh pr list` (limit 200) and 6 other subprocesses (P3, estimated)

- **Location:** `claude/plugins/artifacts/scripts/hook_session_start.py:57-62` (`list_pull_requests`, `GH_TIMEOUT = 30` at `:36`), plus `git log -G url` over 200 commits in `hook_after_command.py` `origin_record_file` (`:115`).
- **Cost per call:** 211 ms measured without network. With network a `gh pr list --limit 200` is usually 0.5 to 1.5 s (estimate); it cannot exceed 30 s.
- **Scenario:** Once per session start and after `/clear` or resume. It is off the per-tool-call path, so the effect is a slower first prompt, not a slower session.
- **Fix:** Use `--limit` close to the number of open tasks, or skip the catch-up when the registry has no task in a state that a merge would change. Cache the result for a few minutes.

### Finding 6: Docs Stop hook runs 5 `git` processes every turn end (P3, measured)

- **Location:** `claude/plugins/docs/scripts/hook_stop.py:17-27` through `docs_lib.py:302-350` (`default_base`, `changed_files`, `commit_messages`) and `docs_check.py:239` (`check_map`).
- **Cost per call:** 55 ms measured, 5 `git` processes.
- **Scenario:** Every turn end in a repository with `docs/docs.json`. Small and flat. The cost grows with the size of the diff, not with history, so no worry yet.
- **Fix:** None needed now. If wanted: combine `rev-parse`, `merge-base` and `diff` into fewer calls, and skip when `git status --porcelain` is empty and `HEAD` equals the last checked commit.

### Finding 7: `gh` calls in `gh pr merge` pre-check (P3, estimated)

- **Location:** `claude/plugins/delivery/scripts/hook_pre_tool.py:66-110` (`check_merge`: `repo view`, `pr view`, and for a foreign repo `run list`).
- **Cost per call:** 2 to 3 `gh` calls, about 1 s with network (estimate). Only on a `gh pr merge` command, which is rare.
- **Scenario:** One merge per train. Not a hot path.
- **Fix:** None needed. Optionally skip `repo view` when `-R` is absent.

### Finding 8: `blocks.log` and `current_branch` (P3, no measurable cost)

- **Location:** `claude/plugins/delivery/scripts/hooklib.py:477-487` (`log_block` appends forever, no rotation); `hook_pre_tool.py:215` (`current_branch` starts `git rev-parse` only for the branch gate commands).
- **Cost per call:** under 1 ms to append. One line is about 200 bytes, so 10 MB takes about 50,000 blocks.
- **Scenario:** Only when `log_every_block` is on. Effectively unbounded but very slow growth.
- **Fix:** Truncate to the last 2,000 lines when the file passes 1 MB.

## Areas that are fine

- **Python start-up and imports.** Hook scripts are 33 to 55 ms warm against 12 ms bare Python. No heavy imports on the hot path (`ctypes` is imported only on Windows).
- **Bounded state files.** The delivery per-session state keeps 40 sessions (`hooklib.py:34`), the artifacts stop state keeps 40 (`hook_after_command.py:46`), the load cache keeps 3 samples (`load.py:30`), and ledger `events` keep 500.
- **Load cache is written atomically** (`load.py:254`), and a failed measurement fails open.
- **Light Bash and non-matching tools** cost no subprocess in the delivery hooks. `hook_pre_tool.py` starts `git` or `gh` only for specific commands.
- **Docs Session start** is 44 ms and does nothing outside a docs project.
- **Artifacts event queue** (`artifact_queue.py:160`) is de-duplicated per (task, status, event), and events are removed when applied.
- **Timeouts.** Every `gh` and `git` call has a timeout, and every hook fails open, so one degraded dependency cannot block a session. The sum of timeouts is large (30 s `gh` in artifacts, 25 s per call in DL-76), but they apply only when the network is bad.
- **`ci_watch.py`** polls every 30 s by default with one `gh` call per poll, and gives up after repeated errors. Fine for a watcher.
- **Retries.** No retry loops without a cap were found in the scope.

## Scope and what was not covered

Covered:

- Every entry point in `claude/plugins/*/hooks/hooks.json`: delivery (PreToolUse, PostToolUse, PostToolUseFailure, UserPromptSubmit, Stop, SessionStart), artifacts (PostToolUse, PostToolUseFailure, Stop, SessionStart), docs (Stop, SessionStart). Read: `hooklib.py`, `load.py`, `load_guard.py`, `hook_*.py` in the three plugins, `artifact_queue.py`, `docs_lib.py`, `docs_check.py` (`check_map`).
- Timing with a realistic stdin payload (15 runs, 7 for the ledger and load-cache tests), subprocess counts with a `Popen` wrapper, `cProfile` of `project_artifacts.py pending`, ledger growth with synthetic rows (up to 20,000 per list).

Not covered:

- **Network cost.** The container has no GitHub host, so every `gh` figure is an estimate (marked "estimated").
- **Other machines.** Only Linux was measured. The macOS path (`top -l 2`, about 1 s plus `sysctl`) and the Windows path (a 1 s sleep, as on Linux) were read, not run.
- **Hook scripts in the `delivery` scripts folder of the project-setup template** (`.../tooling/shared/scripts/delivery/`, about 8,000 lines). Read only for polling, sleeps and `gh` use (`ci_watch.py`, `delivery_common.py`). Their run time was not profiled. They run on demand, not on tool calls.
- `transcript-folds` (a TypeScript UI module, not a hook run per call) and the `audits` plugin.
- `render_artifacts.py` and `project_artifacts.py` beyond `pending` (render and publish commands, not hook paths). `delivery_watch.py`, `delivery_doctor.py` and `docs_*` CLI scripts other than the checks above.
- Memory and concurrency: two hooks writing the same ledger at the same time are serialised by `locked()`; its wait time was not measured.
- No mutation passes, Docker or full suites were run.
