# DS66: delivery learnings inventory and ledger schema (draft)

Status: read-only study, 14 Oct 2026. Not committed. Inputs: a real project's session memory, the user and project CLAUDE.md
files and rules, `~/.claude/hooks/no-tomorrow.mjs`, the dev-standards plugins (artifacts hooks,
claude-setup assets, tech-stack-setup `scripts/delivery/*`), and that project's repository (its delivery scripts and CI workflow).

Goal: every delivery and orchestration learning becomes a mechanical check (hook, script or
ledger field) in the plugins, not a memory note the orchestrator must remember.

Legend
- **Scope**: G = generic (belongs in a plugin), P = project-specific (per-project config or the
  project's own scripts).
- **Kind**: STOP = Stop-hook block; PRE = PreToolUse deny; POST = PostToolUse ledger write;
  SS = SessionStart; WATCH = watcher script; CI = CI guard test; GIT = git hook; TEXT = rules text only.
- **Today**: Y = enforced, W = warns only, ~ = partly, N = not enforced (memory or rules text only).

## 1. Learnings

### 1a. Trains, CI and merge

| ID | Rule (imperative) | Source | Scope | Kind | The check reads | Today |
|---|---|---|---|---|---|---|
| DL-01 | Never push to a branch whose ready PR's CI is running; late work rides the next train. | delivery-speed-process (S3), rules | G | GIT pre-push + PRE `git push` | `gh pr list --head`, `gh run list --commit`; `trains[].ci.state` | Y `train_freeze.py` via `.githooks/pre-push` (both repos); not as PRE |
| DL-02 | Join and check the next train while the previous train's CI runs; push it the moment that CI is green. | next-train-at-green | G | STOP | `trains[k].green_at` set, `trains[k+1].state=joined`, `pushed_at` null > 5 min | N |
| DL-03 | Merge a green train at once; never leave a green train unmerged (RELEASE-27 sat green ~10 h). | dialogs-block-the-turn, standing-release-mandate | G | STOP + WATCH | `trains[].green_at` set, `merged_at` null, no `hold` reason | N |
| DL-04 | Before any question dialog, do every action that does not need the answer (merges, pushes, launches, publish). | dialogs-block-the-turn | G | PRE `AskUserQuestion` | ledger "actionable now" set (DL-02/03/24 conditions true) | N |
| DL-05 | Never `gh pr merge --auto`. | never-gh-auto-merge, rules | G | PRE | command tokens | N (rules text; `session_guard.py` does not cover it) |
| DL-06 | Merge only after `ci_watch.py` passed for the PR's current head SHA. | never-gh-auto-merge, rules | G | PRE `gh pr merge` | `trains[].ci.head_sha == gh pr view headRefOid` and `ci.state=success` | ~ `ci_watch.py` exists; merge not gated |
| DL-07 | Watch CI by the workflow runs of the head commit, never by the PR check list. | rules | G | PRE (deny `gh pr checks --watch`) | command tokens | ~ `ci_watch.py`; nothing stops the other way |
| DL-08 | Open a ready PR only from a release/integration branch; every other PR is a draft. | CLAUDE.md, rules | G | PRE | branch name vs `release_branches` | Y `session_guard.py` ready-PR guard (wired in a real project's settings) |
| DL-09 | Check runners are online for every label CI needs before opening a ready PR. | delivery-speed-process (S7) | G | PRE `gh pr create`/`ready` + WATCH | `runners[]` (`gh api .../actions/runners`), `runs-on` labels | W `runner_health.py` (join, ci_watch), `runners-check.ts` (P) |
| DL-10 | A ready PR from `release/*` runs `release:prepare` (fold spec notes) before CI. | away-2026-10-13-late-night 03:40 | G (change_notes) | PRE `gh pr create`/`ready` | `change_notes.py --check-folded` exit | ~ CI fails late (`--check-folded`) |
| DL-11 | A join is light: merge, resolve conflicts, fold spec notes, typecheck + lint of the touched packages, the fast guards (pre-push), then push and open the ready PR at once; never the branch gate or a full suite on the joined head, no wait for a sandbox gate before the ready PR, no full gate re-run after a join fix. The ready PR's CI is the one full run. | join-quick-check-not-full-suite, check-long-jobs-logs | G (+P steps) | PRE (test guard) |`gate.json` join steps (`"join"` flag, `join_guards`), `.delivery/join-result.json`| Y `join.py` light check + `session_guard.py`; `hook_pre_tool.py` PreToolUse deny (branch gate on a release/integration branch, join brief naming it) |
| DL-12 | Each agent runs one affected branch gate, never `--full` unless a valve trips. | delivery-speed-process (S1) | G | PRE | command tokens, valve files changed | Y `session_guard.py` test guard, `branch_gate.py` default |
| DL-13 | Trust an agent branch's gate only via `gate-result.json` matching current head and base; the join checks it per branch, never for the joined head or the ready PR. | rules | G | script | `refs/gate-results/<b>` | Y `gate_verify.py`, `join.py` |
| DL-14 | After a merge run `cleanup.py --pr N`; leave no merged branch or finished worktree. | cleanup-branches-worktrees, rules | G | STOP + POST | `trains[].merged_at` set, `cleaned_at` null; the message names the project's `cleanup_command`, then `delivery_ledger.py cleaned --pr N`, which verifies the branches and worktrees are gone and records `cleaned_at` on every row with that pr | ~ `cleanup.py`, `train-cleanup.yml` (remote); local not forced |
| DL-15 | A ready/train PR body lists the drafts it carries (`Carries: #x, #y`). | delivery-speed-practices 10-06 | G | PRE `gh pr create` (ready) | `--body` text vs `trains[].cargo[].pr` | N |
| DL-16 | A train leaves with what is green; it never waits for the slowest cargo. | delivery-speed-practices (TL11), no-next-day-deferral | G | STOP (warn) | `trains[].cargo[].gate` all green except members still building > 15 min after first green | N |
| DL-17 | One train in CI at a time; on the timeline, a wait is a gap, never a phase. | next-train-at-green | G | POST (phases from events) | `trains[].phases.actual` written only by events | N (hand-drawn chart) |
| DL-18 | One deploy per merge; smoke-test production after it; fix forward on a new branch; ask before a rollback when the owner is awake. | CLAUDE.md, delivery-speed-practices 10-07 | G | STOP | `trains[].merged_at` set, `smoke.state` null; the message names the project's `smoke_command`, then `delivery_ledger.py smoke --pr N`, which reads the newest `smoke_workflow` run on the merge commit and records `smoke` and `live_at` on every row with that pr | ~ deploy-job smoke (CI); `smoke_packaged.py` for packaged apps |
| DL-19 | Vercel deploys only from the default branch; no preview deploys for agent branches; never merge mid-round to see it deployed. | CLAUDE.md | G | PRE (`vercel deploy` without `--prod`, on non-default branch) | git branch, command | ~ `git.deploymentEnabled` config |
| DL-20 | Never `vercel env rm` to narrow targets; after an env change re-list Production. | vercel-env-rm | G | PRE (deny `vercel env rm`) + POST (queue a re-list) | command tokens | N |
| DL-21 | CI and installer jobs run only on self-hosted runners; never a GitHub-hosted `runs-on`. | CLAUDE.md | P (G as option) | CI | workflow YAML | Y `packages/windows-installer/src/ci-workflows.test.ts` |
| DL-22 | Build artifacts: keep only the newest of each stable name. | rules | G | CI | artifacts list | Y `artifact-prune.yml` / `artifact_prune.py` |
| DL-23 | A gate that fails at `setup` = stale lockfile: regenerate and commit, never install unfrozen. | rules | G | PRE (deny `--no-frozen-lockfile`, `npm install` in gate context) | command tokens | N |
| DL-24 | Spec change notes are folded only by the release PR; never commit with conflict markers. | delivery-speed-practices 10-05 | G | GIT pre-commit | staged diff for `^<<<<<<<` | ~ `change_notes.py`; marker check not confirmed |
| DL-25 | Put catalogue/matching cargo (the long pole) in the earliest train. | delivery-speed-practices 10-05 | P | TEXT (proxy: runner_plan order) | `trains[].cargo[].paths` vs long-pole globs | N |
| DL-26 | Merge+deploy and catalogue publish need no click when the full suite is green and the owner library measures zero regressions. | standing-release-mandate | P | STOP (via DL-03) + PRE merge | `trains[].measure.state` when cargo touches matching paths | N |
| DL-27 | Measure every matching/catalogue change on copies of the owner library inside the agent loop, never first at the release gate. | speed-without-compromise | P | PRE `gh pr merge` | `trains[].measure`, cargo paths | N |

### 1b. Agents

| ID | Rule (imperative) | Source | Scope | Kind | The check reads | Today |
|---|---|---|---|---|---|---|
| DL-30 | Size each agent ETA from scope: setup + work by files touched + affected checks; state the breakdown; never pad. | agent-eta-by-scope | G | POST (on launch) + STOP | `agents[].eta.breakdown` present; total vs `eta_table` (small fix 15-25, UI 25-35, multi-list 40-60) | N (the registry has `expected_basis`, R6.10, but nothing ties it to a launch) |
| DL-31 | Every ETA is a clock time from the run's real start + typical duration, naming the dependency; no "tomorrow" unless computed past midnight. | no-next-day-deferral | G | STOP | last assistant text; `agents[].started`, `trains[].ci.started` | ~ `~/.claude/hooks/no-tomorrow.mjs`, registered only in a project's `settings.local.json` (not a plugin) |
| DL-32 | Check each critical-path job's own log every ~30 min; a log older than its step's typical time = investigate now. | check-long-jobs-logs | G | WATCH + STOP | `agents[].log_path` mtime, `agents[].last_checked`, `jobs[].log_path` | N |
| DL-33 | Never end a turn with work in flight without a background watcher that wakes within 20 min. | delivery-speed-practices 10-06/10-07 | G | STOP | in-flight set (agents running, trains in CI, installs) vs `watchers[].heartbeat_at` | ~ artifacts Stop hook only asks for a Running task (R8.10) |
| DL-34 | After a routine reports succeeded, verify its branch moved before counting it done. | delivery-speed-practices 10-06 | G | WATCH | `git ls-remote` sha vs `agents[].base_sha` | N |
| DL-35 | Start cloud runs at once (`run_once_at` = now + ~1 min). | delivery-speed-practices | G | PRE `RemoteTrigger` | `run_once_at` vs clock | N |
| DL-36 | Every cloud brief carries: no push notifications, the CRITICAL RUN RULE (never end the turn while waiting, push early), no attribution, the shared BRIEF.md, one affected gate. | agent-models, delivery-speed-practices, no-attribution | G | PRE `RemoteTrigger`/`Agent` | prompt text vs `config.brief_markers[]` | N |
| DL-37 | Code agents: Sonnet at medium; Opus agents medium; RemoteTrigger sets `session_context.effort_level`. | agent-models, rules | G | PRE `Agent`/`RemoteTrigger` | `effort` / `effort_level` / `model` fields | ~ `effort_drift.py` (SessionStart, settings only) |
| DL-38 | Concurrency caps: cloud 8 (owner may raise per night), local <= 3 and only with > 8 GB free memory; rules cap 5 at once. | agent-models, rules | G (caps in config) | PRE `Agent`/`RemoteTrigger` | count `agents[state=running]` by `where`; free memory | N |
| DL-39 | Non-PC-bound work goes to cloud runs until the cloud cap is full; local only for PC-bound steps. | agent-models, merge-work-use-cloud | P | PRE `Agent` (local) | prompt has `PC-bound:` reason, or cloud running == cap | N |
| DL-40 | One agent and one branch carry every open task in the same files/area; split only large, truly parallel parts. | delivery-speed-process, merge-work-use-cloud | G | PRE (context only) | registry To do/Waiting tasks with the same app/area | N (gap, see 3) |
| DL-41 | Split parallel agents by file ownership; never chain an agent on files another running agent owns. | delivery-speed-practices, rules | G | PRE `Agent`/`RemoteTrigger` | `agents[].owns[]` overlap | N |
| DL-42 | Agents stop only processes and containers they started; never kill by name or stop every container. | rules | G | PRE | command tokens (`taskkill /IM`, `pkill`, `docker stop $(docker ps -q)`) | N |
| DL-43 | Before briefing an agent that needs an external site, run `reach_check.py`; fetch locally on failure. | rules | G | PRE `RemoteTrigger` (when prompt has URLs) | `reach_checks[]` within 1 h | ~ script exists, not required |
| DL-44 | Agents write their report first and push after every step. | rules | G | TEXT (proxy DL-34) | branch activity | N |
| DL-45 | Commit shared contracts to the integration branch before launching agents. | rules | G | PRE `RemoteTrigger` | brief names a contract path that is on `origin/<integration>` | N |

### 1c. Local machine, runners, installs

| ID | Rule (imperative) | Source | Scope | Kind | The check reads | Today |
|---|---|---|---|---|---|---|
| DL-50 | One heavy local job at a time; heavy jobs yield to train CI and pause the local runner for their duration, always resuming it. | ci-runners-on-this-pc, owner-answers-2026-10-14-morning, delivery-speed-practices | G (runner_plan) / P (heavy-job.ts) | PRE (heavy command not via wrapper) + WATCH | `runners[].busy/paused_by`, `jobs[state=running, heavy]` | ~ a project's own heavy-job script; nothing forces the wrapper |
| DL-51 | Never add CI runners on this PC; weigh memory before heavy local work. | ci-runners-on-this-pc | P | TEXT + WATCH (memory) | free memory | N |
| DL-52 | Start every local operator/node:sqlite job pinned off cores 10/11 at BelowNormal. | ci-core-mask | P | PRE (wrapper) | command via wrapper | ~ CI mask task; local jobs by hand |
| DL-53 | Worktrees and scratch only under the work root (`C:\Work\...`), never under the projects folder or `.claude/worktrees`; remove when done. | work-folders | G (root in config) | PRE `git worktree add`, `EnterWorktree` | path vs `config.work_root` | N |
| DL-54 | Installers are built and published only by the pipeline; local builds only to test. | local-installer-releases | P | PRE (deny local publish command) | command tokens | N |
| DL-55 | Installs run through the SYSTEM update tasks (no UAC), one at a time; a second install waits. | update-feedback, away-2026-10-13-late-night | P | PRE (`msiexec`, `schtasks /run ...UpdateNow`) + POST | `installs[state=installing]` | N |
| DL-56 | Build and install operator/home MSIs on this PC and verify before pushing such changes. | install-locally-before-push (superseded in part by pipeline auto-update) | P | TEXT | `installs[]` for the product at the train's version | N |
| DL-77 | No memory above 85% and no CPU above 60% on the machine: while either is over its limit, start no new heavy work (test runners, builds, installs, docker, ffmpeg, background jobs, local agents, workflows). Cloud launches are never held. Never kill or slow anything running. | owner rule 23 Oct 2026 (two crashes under file-load peaks) | G | PRE `Bash`, `PowerShell`, `Agent`, `Workflow` (exit 2) | total memory % and CPU % (load.py, ~1 s CPU window, 10 s cache); limits: project `load_limits` over `~/.claude/luismc-delivery-machine.json` over 85/60; heavy list in the plugin README and `heavy_commands` | Y (on in every project where the plugin is enabled, with or without `.delivery/`; fails open with a warning when the machine cannot be measured) |
| DL-78 | When the machine is over a limit, say so once per turn (numbers and limits) so the session holds new work. | owner rule 23 Oct 2026 | G | STOP + SS (non-blocking `systemMessage`; SessionStart also `additionalContext`) | same sample as DL-77 | Y |
| DL-79 | A self-hosted runner starts a job only when the machine is under the DL-77 limits: `runner_load_gate.py` is the runner's `ACTIONS_RUNNER_HOOK_JOB_STARTED` hook, polls every 15 s for up to 30 min (then fails the job with a log line), and the doctor reports whether the hook is set. | owner rule 23 Oct 2026 | G | WATCH (runner hook) + doctor `runner` check | same sample; `ACTIONS_RUNNER_HOOK_JOB_STARTED` in the environment or a runner folder's `.env` | Y when installed (the plugin changes no runner configuration) |

### 1d. Progress page and reporting

| ID | Rule (imperative) | Source | Scope | Kind | The check reads | Today |
|---|---|---|---|---|---|---|
| DL-60 | On every task state change, update the task and publish Full Progress in the same turn. | progress-on-every-change | G | STOP | `pending --json` | Y artifacts `hook_end_of_turn.py` (R8.3) |
| DL-61 | Publish Full Progress at least hourly at the top of the hour when nothing was published in the last 60 min; the session creates the hourly cron at start. | full-progress-hourly | G | SS + WATCH + STOP | `publishes[full-progress].last_at` | N (memory; cron made by hand) |
| DL-62 | Every publish = `pending --json` -> publish the path it prints -> `mark-published`; check the version went up. | full-progress-publish-copy | G | POST (Artifact publish) + PRE `mark-published` | copy mtime/hash vs `publishes[].last_state_hash`, published version | ~ plugin 1.9+ flow; no check that the copy was fresh |
| DL-63 | When a release ships, close every row it carries; no open row may show an Expected time in the past. | progress-on-every-change | G | STOP | registry `expected` vs now; `trains[].cargo[].task` | N |
| DL-64 | Say RELEASE-n to the owner, never train labels or branch names. | release-names | G (naming in config) | STOP (text scan) | last assistant text vs `config.train_label_re` | N |
| DL-65 | Every status shown (page, chat) comes from one shared reading of the latest state. | status-from-one-truth | G | design: renderers read the ledger | ledger only | N (applies to the ledger itself) |
| DL-66 | Show times in the owner's zone, labelled (Lisbon); stamp from the real clock, never a guess. | owner-timezone, progress-on-every-change | G (tz in config) | POST stamps | clock | ~ artifacts script stamps |

### 1e. Owner communication and attribution

| ID | Rule (imperative) | Source | Scope | Kind | The check reads | Today |
|---|---|---|---|---|---|---|
| DL-70 | Ask every open question at once, numbered, several dialogs in one message if more than 4; never trickle. | all-questions-every-time, all-questions-at-once, CLAUDE.md | G | PRE `AskUserQuestion` (context) | count of open `owner_questions[]` vs this call | Y (rules text delivered by SessionStart; Q-5 trickle check in PRE) |
| DL-71 | Never write explanations before a dialog in the same turn; put context inside the question or ask in plain chat. | explain-before-question-tool | G | PRE `AskUserQuestion` | transcript: assistant text since last user message > ~300 chars | N |
| DL-72 | A rejected dialog with no owner words is not a stop: keep working, re-ask in plain chat. | question-tool-rejection | G | POST-failure `AskUserQuestion` (context) | tool error text | N |
| DL-73 | Never send email, messages, posts, issues or comments in the owner's name; drafts as files. | never-send-as-owner, user CLAUDE.md | G | PRE (outbound: `gh issue/pr comment`, `gh issue create`, mail/Slack MCP send) | tool name, command | ~ auto-mode classifier only |
| DL-74 | No Co-Authored-By or Claude attribution in commits or PR bodies (owner choice). | no-attribution | G (owner opt) | GIT commit-msg + PRE `git commit`/`gh pr create` | message/body text | N; violated by a project CI auto-fix script |
| DL-75 | Create every doc under `docs/`. | rules | G | PRE `Write` of `*.md` | path | N |
| DL-76 | A release runs CI once: nothing after the merge re-runs what the release PR proved on the same tree; only publish, deploy and production smoke run on the default branch. | one-ci-per-release | P | STOP | PR merge commit tree vs PR head tree; default-branch runs of that commit and their jobs vs `pr_proven_jobs` | N |

Counts: 66 learnings (DL-01..27, 30..45, 50..56, 60..66, 70..79). Enforced today: 8 Y,
1 warn-only (W), 17 partly (~), 37 not enforced (N).

## 2. Ledger schema: `.delivery/ledger.json`

One file per repository (git-ignored with `.delivery/`), written only through
`delivery_ledger.py` (atomic write via temp + rename, a lock file, `schema: 1`). Hooks never edit
it by hand; every field below names its writer. Readers: the Stop/PreToolUse hooks, the watcher,
the Full Progress renderer (DL-65: the one truth for shown state).

```jsonc
{
  "schema": 1,
  "updated_at": "ISO-UTC",
  "config_ref": ".delivery/config.json",        // caps, work_root, brief markers, tz, labels
  "trains": [{
    "id": "T-2026-10-14-01",                       // ledger id
    "release_no": 29,                              // RELEASE-n (from the artifacts record)
    "branch": "release/29",                        // ready PR head
    "pr": 412,
    "state": "planned|joining|joined|pushed|ci|green|red|merged|live|cleaned|abandoned",
    "hold": null,                                  // {"reason": "...", "by": "owner|rule", "until": ISO}
    "cargo": [{"task": "DV148", "branch": "DV148-fix", "pr": 409, "sha": "…",
               "gate": "pass|fail|none", "joined_sha": "…", "paths": ["apps/web/**"]}],
    "phases": {
      "planned": [{"name": "join|ci|merge|deploy|smoke|install", "start": ISO, "end": ISO, "basis": "…"}],
      "actual":  [{"name": "…", "start": ISO, "end": ISO}]   // gaps are implied, never a phase (DL-17)
    },
    "ci": {"head_sha": "…", "run_ids": [123], "state": "queued|running|success|failure", "started_at": ISO},
    "measure": {"state": "none|clean|regressions", "at": ISO, "report": "path"},
    "smoke": {"state": null, "at": ISO},
    "joined_at": ISO, "pushed_at": ISO, "green_at": ISO, "merged_at": ISO,
    "live_at": ISO, "cleaned_at": ISO
  }],
  "agents": [{
    "task": "DV152",                               // task id(s); "tasks": [...] when bundled
    "where": "local|cloud",
    "id": "trig_… | agent id",                     // RemoteTrigger id or Agent task id
    "session": "cse_…",                            // cloud session when known
    "branch": "DV152-scripts", "base_sha": "…", "head_sha": "…",
    "owns": ["scripts/delivery/**"],              // file ownership (DL-41)
    "model": "sonnet", "effort": "medium",
    "started": ISO,
    "eta": {"total_min": 25, "breakdown": {"setup": 5, "work": 12, "checks": 8},
            "basis": "2 small scripts", "due": ISO},
    "log_path": "C:/…/run.log",                    // local agents and jobs
    "last_checked": ISO, "last_activity": ISO,     // branch moved or log mtime
    "state": "queued|running|pushed|done|empty|stalled|failed|stopped"
  }],
  "jobs": [{"id": "B14-build", "cmd": "…", "heavy": true, "pid": 1234, "log_path": "…",
            "started": ISO, "typical_step_min": 20, "last_checked": ISO, "state": "running|done|failed|waiting-ci"}],
  "installs": [{"product": "home|operator", "version": "0.1.6212", "via": "HomeUpdateNow",
                "state": "queued|installing|done|failed", "started": ISO, "ended": ISO, "log": "…"}],
  "publishes": [{"artifact": "full-progress", "url": "https://claude.ai/artifact/…",
                 "last_at": ISO, "last_version": 512, "last_state_hash": "sha256 of the publish copy",
                 "copy_written_at": ISO}],
  "runners": [{"name": "build-pc-linux", "labels": ["self-hosted","Linux","project-linux","project-linux-big"],
               "online": true, "busy": false, "local": true,
               "paused_by": null,                  // job id while heavy-job pauses it
               "checked_at": ISO}],
  "watchers": [{"pid": 4321, "kind": "delivery_watch", "started": ISO, "heartbeat_at": ISO}],
  "owner_questions": [{"id": "Q7", "text": "…", "asked_at": ISO, "answered_at": null, "blocks": ["T-…"]}],
  "events": [{"at": ISO, "kind": "…", "ref": "…", "by": "writer"}]   // append-only, capped (last 500)
}
```

### Who writes each field

| Field | Writer |
|---|---|
| `trains[]` create, `cargo[]`, `release_no`, `phases.planned` | `delivery_ledger.py train plan` (orchestrator; release_no from the artifacts record) |
| `cargo[].gate`, `cargo[].joined_sha`, `joined_at`, `state=joined` | `join.py` (calls the ledger module after each merge and after the light check) |
| `pushed_at`, `state=pushed` | POST hook on `git push` of a train branch (and `join.py --push`) |
| `pr`, `state=ci` | POST hook on `gh pr create` / `gh pr ready` (parses the PR URL) |
| `ci.*`, `green_at`, `state=green/red` | `ci_watch.py` (on decide); the watcher between calls |
| `merged_at`, `state=merged` | POST hook on `gh pr merge` exit 0; session-start catch-up via `gh pr list --state merged` |
| `live_at`, `smoke` | deploy smoke step / `delivery_log.py live` mirrored; POST on smoke command |
| `cleaned_at` | `cleanup.py --pr N` |
| `measure` | the project's measure script via `delivery_ledger.py measure` |
| `phases.actual` | derived by the ledger module from the timestamps above (never typed) |
| `hold` | `delivery_ledger.py hold` (orchestrator; owner reason required) |
| `agents[]` create (id, where, model, effort, started, eta, owns) | POST hook on `Agent` / `RemoteTrigger create|run` (parses tool input and result; eta/owns from a fenced `delivery:` block in the brief) |
| `agents[].head_sha`, `last_activity`, `state` | watcher (`git ls-remote`, routine `list_runs` status, log mtime) |
| `agents[].last_checked` | POST hook when the session reads that agent's log/branch/run status; watcher never sets it |
| `jobs[]` | `heavy-job` wrapper / `runner_plan.py run` on start/end; watcher for mtime |
| `installs[]` | POST hook on `msiexec` / `schtasks /run …UpdateNow`; watcher reads the product's update-state file |
| `publishes[]` | POST hook on `Artifact` publish (url, version) and on `project_artifacts.py pending`/`mark-published` (hash, copy time) |
| `runners[]` | `runner_health.py` and the watcher (`gh api …/actions/runners`); `paused_by` by the heavy-job wrapper |
| `watchers[]` | the watcher itself (heartbeat each loop) |
| `owner_questions[]` | POST hook on `AskUserQuestion` (asked) and on the next user message (answered) via UserPromptSubmit |
| `events[]` | every writer (append) |

## 3. Gaps: not mechanically enforceable, and the best proxy

| Rule | Why not mechanical | Best proxy |
|---|---|---|
| DL-40 bundle related tasks into one agent | "same area" and "large" are judgment | PRE on launch injects the open To do/Waiting tasks with the same app/owner and the running agents' `owns[]` overlap as additionalContext; deny only when a running agent owns the same paths (DL-41) |
| DL-30 ETA sizing honesty | true scope unknown to a hook | require the breakdown block; warn when total > 2x the `eta_table` row for the declared size; record actual vs ETA in `events` and show the ratio on Full Progress so padding is visible |
| DL-25 long pole first | needs knowing which cargo gates a later step | config `long_pole_globs`; Stop warns when a later train carries them while an earlier one does not |
| DL-27 measure on the real library in the agent loop | the agent sandbox may not reach the library | PRE `gh pr merge` deny when cargo touches `measure_globs` and `trains[].measure.state != clean` |
| DL-44 report first, push after every step | inside the agent's own session | brief marker (DL-36) + watcher marks `stalled` when the branch has not moved for `2x eta.breakdown.work` |
| DL-50/51 memory weighing | memory is machine state, thresholds vary | `runner_plan.py` reads free memory and running heavy jobs; PRE on known heavy commands outside the wrapper |
| DL-56 install locally before push | partly superseded by pipeline auto-update | `installs[]` record for the train version; Stop warns after `live_at` when no install row |
| DL-70 "all questions" | whether every open decision is listed is judgment | `owner_questions[]`: PRE on a dialog adds the list of unanswered ledger questions not in this call; STOP warns when a later turn asks new questions while older ones stay unasked |
| DL-71 no text before a dialog | text length is a crude signal | PRE deny once when > ~300 chars of assistant text precede the dialog in the turn; reason says "end the turn with the text, ask in plain chat" |
| DL-72 rejected dialog is not a stop | needs reading intent | POST-failure context line only |
| DL-65 one truth | design property | the ledger is the only source the renderer and hooks read; a guard test fails if a hook parses chat for state |
| speed-without-compromise, parallel-by-default | goals, not checks | STOP lists "startable now" items (To do tasks with deps met while slots are free; trains green and unpushed) once per turn |
| DL-73 never send as owner | outbound tools are open-ended | deny list of known outbound commands/MCP tools in config; the classifier stays the backstop |

## 4. Build split: four parallel briefs by file ownership

Shared contract first (commit to the integration branch before launch): this file's section 2
as `claude/plugins/delivery/references/ledger-schema.json` (JSON Schema) and the config shape
`.delivery/config.json` (caps, work_root, tz, brief_markers, train_label_re, long_pole_globs,
measure_globs, eta_table, heavy_commands, outbound_deny). Proposed home: a new plugin
`claude/plugins/delivery/` (`luismc-delivery`), so the artifacts plugin stays to ARTIFACTSPEC.

**(a) Ledger + PostToolUse + watchers**
- `claude/plugins/delivery/scripts/delivery_ledger.py` (module + CLI: plan, hold, measure, show, lock, atomic write, derive phases)
- `claude/plugins/delivery/scripts/hook_post_tool.py` (PostToolUse/PostToolUseFailure for Bash, Agent, RemoteTrigger, Artifact, AskUserQuestion; UserPromptSubmit answer marking)
- `claude/plugins/delivery/scripts/delivery_watch.py` (background watcher: ls-remote, run status, log mtimes, runners, installs, heartbeat)
- `claude/plugins/delivery/references/ledger-schema.json`
- tests: `claude/plugins/delivery/tests/test_ledger*.py`, `test_post_tool*.py`, `test_watch*.py`
- small call-ins (same agent, to avoid split ownership): `tech-stack-setup/.../scripts/delivery/{join,ci_watch,cleanup,runner_health}.py` gain a best-effort `ledger.record(...)` call (no-op when the module is absent)

**(b) Stop / PreToolUse / SessionStart hooks**
- `claude/plugins/delivery/hooks/hooks.json`
- `claude/plugins/delivery/scripts/hook_stop.py` (DL-02, 03, 14, 16, 18, 31 (port `no-tomorrow.mjs`), 32, 33, 61, 63, 64; block-once-per-fingerprint and a 3-block ceiling like R8.4)
- `claude/plugins/delivery/scripts/hook_pre_tool.py` (DL-04, 05, 06, 07, 09, 10, 15, 19, 20, 23, 35-39, 41-43, 45, 53-55, 71, 73-75)
- `claude/plugins/delivery/scripts/hook_session_start.py` (rule delivery, catch-up of merged trains, the hourly-publish instruction for DL-61, stale watcher restart prompt)
- `tech-stack-setup/.../scripts/delivery/session_guard.py` stays the test/ready-PR guard; (b) adds `--auto` deny there only if the plugin is absent (one owner: this agent)
- tests: `claude/plugins/delivery/tests/test_stop*.py`, `test_pre_tool*.py`, `test_session_start*.py`
- reads the ledger only through (a)'s module; uses fixtures until (a) lands

**(c) runner_plan + artifacts publish-on-change / hourly**
- `tech-stack-setup/.../scripts/delivery/runner_plan.py` (generic heavy-job wrapper: wait for train CI, pause/resume the local runner, one heavy job at a time, memory floor, optional affinity/priority; records `jobs[]`, `runners[].paused_by`; `runners` subcommand = D6a: report offline runners, repair via `runners[].repair` every `retry_seconds` (300), re-run the cancelled train CI, ledger events `runner.offline|repair|retry|online|rerun|giveup`) + its test; a project's heavy-job script becomes a thin caller later (project branch, not here)
- `claude/plugins/artifacts/scripts/hook_end_of_turn.py` (hourly fail-safe: block when `publishes[full-progress].last_at` > 60 min; fresh-copy check DL-62)
- `claude/plugins/artifacts/scripts/project_artifacts.py` (`pending --json` records copy hash/time; `mark-published` refuses when no publish of the current copy is recorded; expired-Expected check DL-63)
- `claude/plugins/artifacts/scripts/publish_hourly.py` (new: what the hourly cron/watcher calls)
- `claude/plugins/artifacts/references/artifactspec.md` + `plugin.json` version bump, artifacts tests

**(d) claude-setup wiring + rules + per-project config**
- `project-setup/skills/claude-setup/SKILL.md` (enable `luismc-delivery`, write `.delivery/config.json`, retire `~/.claude/hooks/no-tomorrow.mjs` and its `settings.local.json` entry once (b) ships)
- `project-setup/skills/claude-setup/assets/.claude/settings.json` (enabledPlugins, PreToolUse entries)
- `project-setup/skills/claude-setup/assets/.claude/rules/agents-and-integration.md` and `clarifying-questions.md` (re-tag each line `<!-- check: … -->` to its new enforcer; add the DL rules that stay text)
- `project-setup/skills/claude-setup/assets/delivery-config.json` (template; example values: caps 8/3/5, work_root `C:\Work`, tz Europe/Lisbon, `release/\d+[a-z]` label regex, measure globs)
- `project-setup/skills/tech-stack-setup/assets/tooling/shared/.githooks/commit-msg` (DL-74, opt-in by config) and `pre-commit` conflict-marker check (DL-24)
- `.claude-plugin/marketplace.json`, `README.md` section for the new plugin, `docs/specs/` DELIVERYSPEC draft
- model-profiles / rule-tag tests that check every `<!-- check: -->` path exists

Order: contract commit, then (a)-(d) in parallel; (b) and (c) code against the schema and
fixtures; the join runs (a) first. Project follow-ups (in that project, own branch): wire the
plugin, add `.delivery/config.json`, drop the `Co-Authored-By` line in its CI auto-fix script,
make its heavy-job script call `runner_plan.py`.

## 5. Owner decisions (14 Oct 2026, 22:3x Lisbon) — binding, they override sections 1-4 where they differ

- D1 Approach B+C: hooks enforce inside sessions; watcher scripts (no model) act on time-critical steps.
- D2 Home: new plugin `claude/plugins/delivery/` named `luismc-delivery`; claude-setup installs, enables and configures it per project (`.delivery/config.json`). Full Progress publishing stays in `luismc-artifacts`; delivery only feeds it (publish-on-phase-change + hourly, brief (c)).
- D3 Stop-hook findings BLOCK (not warn), with the block-once-per-fingerprint and 3-block ceiling pattern of artifacts R8.4.
- D4 Cloud first: PreToolUse DENIES a local `Agent` call unless its prompt carries a `PC-bound:` reason line, or the cloud cap is full (DL-39).
- D5 The watcher pushes the next train, opens its ready PR AND merges the previous train the moment its CI is green for the PR's current head (checked by the script via the head's workflow runs; never `gh pr merge --auto`). Holds (`trains[].hold`) stop it.
- D6 Runner orchestration by the watcher: cancel CI runs a newer push to the same PR replaced; hold (cancel + re-run after) dependabot and other non-train CI runs while a train's CI runs; heavy local jobs yield to train CI (runner_plan).
- D6a Runner offline (owner 14 Oct ~23:25): report it at once, then retry every 5 minutes; each retry first tries to repair the runners (read runner status via the GitHub API, restart the runner service or container the project names in `.delivery/config.json` `runners[].repair`) and only then re-queues or re-runs the CI that needs them. Never just wait. Every report and repair attempt goes to the ledger.
- D7 After a lesson is enforced with its DL id, its old memory note is DELETED (not trimmed). claude-setup reports which memory files map to enforced ids; deletion is done by the orchestrator after the plugin release.
- D8 Questions (replaces DL-70..72):
  - Q-1 every open question in one go; no 4-question cap when the owner says "ask me questions" (several wizard dialogs in one message).
  - Q-2 always the questions wizard (AskUserQuestion), never plain-text questions in the terminal: Stop hook blocks a final reply whose closing part is a numbered/bulleted list of questions to the owner instead of wizard calls.
  - Q-3 context goes INSIDE each question's text (text before a dialog is not seen): PreToolUse denies a dialog whose question texts are too short to stand alone (config min chars).
  - Q-4 merge/push/launch before asking: PreToolUse denies AskUserQuestion while the ledger has an actionable-now item (green train unmerged, joined train unpushed with previous green, launch queued).
  - Q-5 no guessing missing parameters, no trickling: PreToolUse denies AskUserQuestion when this session has running agents (`agents[].launched_by`, state queued/running) and already asked a question batch (`owner_questions[].asked_at`) within `question_window_min` (default 60) since the owner's last prompt (`owner_prompt.at`, written by the UserPromptSubmit recorder); the message says to park the question until the agents of this wave report, then ask everything at once. Allowed: every running agent has `blocked_on: "owner"`; the owner's latest prompt asked for questions (`owner_prompt.asked_for_questions`, "ask me questions"); dialogs issued within `question_batch_sec` (90) of the previous one (Q-1, several dialogs in one message). Switch off with `checks_off: ["Q-5"]`.
  - `clarifying-questions.md` gains Q-2/Q-3 lines and moves under the delivery plugin's rules: `claude/plugins/delivery/rules/clarifying-questions.md` is the canonical text, the SessionStart hook injects it (tags stripped) every session in an opted-in project, and the claude-setup asset is a byte copy kept equal by a plugin test.
- D9 ETA rules (DL-30/31; 0.3.0: a sentence that reports a measured duration, a saving or a cost, or lists two or more durations, is not an ETA, and a clock time or dependency anywhere in the same bullet covers its sentences): breakdown required on every agent launch (`delivery:` block: setup/work/checks minutes); Stop blocks reply text with an ETA lacking a clock time + dependency, or "tomorrow"/"next round" unless computed past midnight; port `no-tomorrow.mjs` into the plugin and retire the user-level hook.

## 6. Project config: `.delivery/config.json` (plugin 0.2.0)

The config is described by `claude/plugins/delivery/references/config-schema.json` and checked by `delivery_config.py validate [--root DIR | --config FILE] [--json] [--strict]` (exit 0 valid, 1 errors, 2 unreadable JSON). Every key is optional and a 0.1.0 config stays valid. A key the schema does not list is a warning, never an error (so a typo shows); keys starting with `_` are comments. A wrong type, an out-of-range number, an invalid regular expression, a `tz` that zoneinfo cannot load, or `--auto` in a merge flag is an error. The aligned reference is a real project's config.

- `enforcement` (Stop and PreToolUse hooks; D3). `mode`: `block` (default) or `warn` (findings and denials are shown as a `systemMessage`, nothing blocks). `block_ceiling` (integer >= 1, default 3): the same findings block this many times per session, then the turn ends (replaces the fixed 3 of artifacts R8.4). `log_every_block` (default false): append every block to `.delivery/blocks.log` as `time<TAB>hook<TAB>rule id<TAB>message` (hook is `stop` or `pre-tool`), for the owner's review.
- `watcher` (D5, D6a). `push_trains`, `open_prs`, `merge_on_green`, `manage_runners`: booleans, all default true (= 0.1.0). `merge_on_green` merges with `gh pr merge N --merge`, never `--auto`, and only when the PR head is the commit whose CI run was green: the watcher re-reads the head right before the merge and passes `--match-head-commit SHA`; a moved head records `merge.head_moved` and waits for the next pass. `merge_method: "merge"` and `merge_flag: "--merge"` are accepted spellings of the only method; `never_auto_merge` documents D5 and cannot be false. `manage_runners`: the watcher launches `runner_plan.py runners` itself (found at `runner_plan.script`, else `scripts/delivery/runner_plan.py`) and relaunches it when it exits (D6a), instead of the project starting it.
- `watcher.ci_workflows` (0.3.0, DL-03): the workflow files that must all complete with conclusion `success` for the PR head commit before a train is green (default `["ci.yml"]`). The latest run of each counts; a missing, running, skipped or failed required workflow is not green, and a sibling workflow (an installer build) never stands in for another. The watcher is the only writer of `green_at`: a `ci_watch.py` pass is recorded as the event `ci_watch.passed` and a failure still marks the train red. A green train whose required run is running again goes back to `ci` and `green_at` is cleared (`train.green_revoked`).
- `stop_repeat_limit` (integer >= 0, default 3), `cleanup_command`, `smoke_command`, `smoke_workflow` (DS72). The Stop hook keeps in `.delivery/hook-state.json`, per session, a fingerprint of each finding and of the ledger fields it depends on (the train row for DL-02, DL-03, DL-14, DL-18 and DL-76, the agent row for DL-30 and DL-32). When the same findings block `stop_repeat_limit` consecutive turn ends with no change to those fields, later turn ends are not blocked for them: one non-blocking notice per session says they are still open and names the recording command, until the fields change or a new finding appears (it blocks normally again). 0 never limits. DL-14 and DL-18 name the project's `cleanup_command` / `smoke_command` (`{pr}` = PR number) and then the recording command: `delivery_ledger.py smoke --pr N [--run ID|URL]` (newest `smoke_workflow`, default `Production smoke`, run on the PR's merge commit; success records `smoke {state: pass, at, run}` and `live_at` on every row with that pr, a failed run records `fail` and exits 1, a missing or unfinished run records nothing and exits 1) and `delivery_ledger.py cleaned --pr N` (the train's branch and cargo branches are gone from `origin` and no worktree holds them, else it lists what is left and records nothing; success records `cleaned_at` and state `cleaned` on every row with that pr). Both write through the ledger lock, touch only those fields, add an event, and never touch CI fields.
- `pr_proven_jobs` (0.3.0, DL-76): job names (case-insensitive, globs allowed) the release PR proves. Rule: "A release runs CI once: nothing after the merge re-runs what the release PR proved on the same tree; only publish, deploy and production smoke run on the default branch." After a train merges and until it is cleaned, the Stop hook reads the merge commit of the PR and, only when its tree equals the PR head tree, lists the default-branch runs of that commit and flags each non-skipped job named here. Default `[]`: the check is off and makes no network call. Any `gh` failure leaves the check silent.
- `load_limits` (DL-77, DL-78): `{"memory_pct": 85, "cpu_pct": 60}`, each 1..100. Precedence per key: `.delivery/config.json`, then the machine file `~/.claude/luismc-delivery-machine.json` (`{"load_limits": {...}}`, optionally `runner_gate` {`max_wait_min`, `poll_sec`, `on_timeout` fail|run} and `runner_dirs` for the doctor), then the defaults 85 and 60. `heavy_commands` (regexes, case-insensitive; plain text also matches) adds commands to the heavy list. The load guard is not opt-in: it runs in every project where the plugin is enabled, with or without `.delivery/`, because it protects the machine. `checks_off: ["DL-77"]` (or `["DL-78"]`) switches a project off; `enforcement.mode: warn` turns the refusal into a message. Heavy: test runners; `pnpm|npm|yarn|bun` scripts `test`, `e2e`, `check*`, `build*` (also via `run`/`exec`/`dlx`); turbo, nx, `tsc -b`, next/vite/webpack builds; cargo, dotnet, go, mvn, gradle, msbuild builds and tests; docker build and compose up/build; ffmpeg; installs (`install|add|ci`) unless `--offline`; background jobs that are not plainly light (git, gh, ls, cat, grep and similar); a local Agent launch (no `isolation` remote/cloud) and any Workflow. Light and never refused: git, gh, ls, cat, grep, rtk-wrapped reads, python one-liners, lint. RemoteTrigger and Agent with remote/cloud isolation are never refused. Over a limit, PRE exits 2 with the numbers, the limits, the top processes by CPU and memory (names only) and what to do (wait or finish a running job). CPU is the mean of the samples of the last 30 s (at most 3), so one spike does not decide.
- `runner_plan` (D6, D6a). `cancel_replaced_runs` (watcher cancels CI runs of a branch whose head has moved on), `hold_dependabot_during_train` (watcher cancels and later re-runs non-train CI runs while a train's CI runs), `heavy_jobs_yield` (`runner_plan.py run` waits for train CI; `heavy_local_jobs_yield` is the same key as a real project spells it): booleans, default true. `retry_seconds`, `runner_max_retries`, `report_command` as in D6a. Without `runner_plan.train_branch_regex`, the top-level `train_branch_re` is used.
- `tz`. An IANA name. If zoneinfo cannot load it (no tzdata, typically Windows) the validator and `delivery_doctor.py` fail, and any hook that still has to format a time prints a warning once before using UTC; it is never silent. SessionStart adds the same warning to its context.
- `delivery_doctor.py [self-check] [--root DIR] [--json]` runs five checks: config valid, gh signed in, tz loads, hooks registered (hooks.json names the hook scripts, and `luismc-delivery` is enabled in project or user settings), ledger writable. Exit 0 all ok, 1 a FAIL, 2 no `.delivery/`.
