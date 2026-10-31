# luismc-delivery

Delivery guard rails for a project that opts in with a `.delivery/` folder. Rules: `docs/architecture/DELIVERYSPEC.md`. Without `.delivery/` the delivery hooks do nothing, **except the machine load guard (below), which is on in every project where the plugin is enabled**: it protects the machine, not the project.

| Script | What it does |
|---|---|
| `hook_*.py` | Stop, PreToolUse, PostToolUse, SessionStart hooks (registered by `hooks/hooks.json`) |
| `delivery_ledger.py` | the ledger `.delivery/ledger.json` |
| `delivery_watch.py` | background watcher: pushes the next train, opens its PR (or adopts the one open PR of a train pushed by hand), merges at green, tidies CI runs, keeps the runner guard running |
| `rules/clarifying-questions.md` | the canonical question rules (Q-1..Q-5); SessionStart injects them every session |
| `delivery_config.py validate` | checks `.delivery/config.json` against `references/config-schema.json` |
| `delivery_doctor.py` | self-check: config valid, gh signed in, tz loads, hooks registered, ledger writable, runner load-gate hook set (DL-79) |
| `load.py`, `load_guard.py` | machine memory/CPU measurement and the load guard (DL-77, DL-78) |
| `runner_load_gate.py` (+ `.cmd`, `.ps1`, `.sh`) | self-hosted runner job-start hook (DL-79) |

## Machine load guard (DL-77, DL-78, DL-79)

Owner rule: **no memory above 85%, no CPU above 60%**; run as many jobs as fit inside that. The guard only holds NEW work. It never kills, suspends or lowers the priority of anything. It is on in every project where the plugin is enabled, **even without `.delivery/`**.

- **Measure** (`load.py`, standard library only): Windows `GlobalMemoryStatusEx` + `GetSystemTimes`; Linux `/proc/meminfo` + `/proc/stat`; macOS `vm_stat` + `top -l 2` (load average fallback). CPU over ~1 s; the last sample is cached 10 s in the temp folder; CPU is the mean of the last up to 3 samples within 30 s, so one spike does not decide.
- **Limits**, per key: project `.delivery/config.json` `load_limits` over the machine file `~/.claude/luismc-delivery-machine.json` over 85/60.

  ```json
  {"load_limits": {"memory_pct": 85, "cpu_pct": 60}}
  ```
- **PreToolUse** (`Bash|PowerShell|Agent|Workflow`): over a limit, a HEAVY call is refused with exit 2 and a message with the numbers, the limits, the top processes (names), and what to do. Heavy: test runners (vitest, jest, pytest, playwright, mocha, `python -m pytest|unittest`); `pnpm|npm|yarn|bun` `test`, `e2e`, `check*`, `build*` (also via `run`, `exec`, `dlx`); turbo/nx; `tsc -b`; next/vite/webpack builds; cargo, dotnet, go, mvn, gradle, msbuild; docker build and compose up/build; ffmpeg; installs (`install|add|ci`) **unless `--offline`** (an install unpacks thousands of files: the crash trigger); background jobs that are not plainly light; a local Agent launch; a Workflow; plus your `heavy_commands` regexes. Light and never refused: git, gh, ls, cat, grep, rtk-wrapped reads, python one-liners, lint. RemoteTrigger and `Agent` with `isolation` remote/cloud are never refused. If the machine cannot be measured the call is allowed with a warning on stderr.
- **Stop / SessionStart**: when over a limit, one non-blocking notice per turn with the numbers (SessionStart also puts it in the model's context).
- **Switches**: `checks_off: ["DL-77"]` / `["DL-78"]` per project; `enforcement.mode: "warn"` shows the refusal as a message; `CLAUDE_DELIVERY_HOOKS=off` disables all hooks.
- **`python3 scripts/load.py`** prints the current numbers (exit 0 under, 1 over, 2 unmeasurable).

### CI runner gate (DL-79)

`scripts/runner_load_gate.py` waits (polls every 15 s, up to 30 min) until the machine is under the limits, logs what it waited for (stdout and `~/.claude/luismc-delivery-runner-gate.log`), then lets the job start. At the maximum it exits 1 so the job fails with a clear log line and can be re-run (`--on-timeout run` lets it go instead). Settings: flags, env `DELIVERY_GATE_MAX_WAIT_MIN`, `DELIVERY_GATE_POLL_SEC`, `DELIVERY_GATE_ON_TIMEOUT`, or `runner_gate` in the machine file. The plugin changes no runner configuration; you install the hook:

- **Linux / macOS runner (systemd service)**: in the runner folder add to `.env`
  `ACTIONS_RUNNER_HOOK_JOB_STARTED=/path/to/luismc-delivery/scripts/runner_load_gate.sh`, then `sudo ./svc.sh stop && sudo ./svc.sh start`. The runner in WSL/Hyper-V needs the plugin folder inside that VM.
- **Windows runner (service)**: add the same line to the runner folder's `.env` with `...\scripts\runner_load_gate.ps1` (or `.cmd`; check your runner version accepts the extension), then restart the service (`Restart-Service "actions.runner.*"`). The runner starts a `.ps1` hook with Windows PowerShell 5.1 (when `pwsh` is absent) as exactly `C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.EXE -command ". 'C:\actions-runner\...runner_load_gate.ps1'"`, as the service's account (often `NT AUTHORITY\NETWORK SERVICE`). Two things must hold for that account, or the script never starts and **every job fails** (the gate's fail-open path cannot run): (1) its PowerShell execution policy must allow the script. The machine default (Restricted) refuses it with a `PSSecurityException`. Set `RemoteSigned` for that account only, from an elevated shell: string value `ExecutionPolicy` = `RemoteSigned` under `HKEY_USERS\S-1-5-20\Software\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell` (`S-1-5-20` is NETWORK SERVICE; another service account has its own SID). (2) It needs read and execute on the Python install the script calls (Python must also be on its PATH). Test it exactly as the runner runs it: a scheduled task whose principal is the service account (`NT AUTHORITY\NETWORK SERVICE`) with that same Execute and Arguments, never `-ExecutionPolicy Bypass` (it passes and hides the problem). Then watch the first real job's log. The doctor reads the policy for the service account and FAILS on Restricted, AllSigned or undefined; it runs nothing and changes nothing.
- Check with `python3 scripts/delivery_doctor.py`: the `runner` line is ok with no runner on the machine, FAIL if a runner folder (`actions-runner*`, `DELIVERY_RUNNER_DIRS`, or `runner_dirs` in the machine file) lacks the hook, or (Windows, `.ps1` hook) the service account's execution policy would refuse it.

## `.delivery/config.json`

Every key is optional; defaults reproduce 0.1.0. Unknown keys warn, `_` keys are comments. Check it with

```
python3 scripts/delivery_config.py validate --root .      # exit 0 valid, 1 errors, 2 unreadable
python3 scripts/delivery_doctor.py                        # exit 0 all ok
```

New in 0.2.0:

```json
{
  "tz": "Europe/Lisbon",
  "enforcement": { "mode": "block", "block_ceiling": 3, "log_every_block": true },
  "watcher": { "push_trains": true, "open_prs": true, "merge_on_green": true, "manage_runners": true },
  "runner_plan": { "cancel_replaced_runs": true, "hold_dependabot_during_train": true, "heavy_jobs_yield": true }
}
```

| Key | Default | Effect |
|---|---|---|
| `load_limits.memory_pct`, `load_limits.cpu_pct` | 85, 60 | project override of the machine load limits (DL-77) |
| `heavy_commands` | `[]` | extra regexes (plain text also matches) that make a command heavy (DL-77) |
| `enforcement.mode` | `block` | `warn` shows findings and denials as a message and blocks nothing |
| `enforcement.block_ceiling` | 3 | the same findings block a session this many times, then the turn ends |
| `stop_repeat_limit` | `block_ceiling` | the Stop hook stops blocking a finding after it blocked this many turn ends in a row with no change to the ledger fields it depends on; 0 = never limit |
| `cleanup_command`, `smoke_command` | unset | the project's commands (`{pr}` = PR number) that the DL-14 and DL-18 messages name before the recording command |
| `smoke_workflow` | `Production smoke` | the workflow `delivery_ledger.py smoke` looks for |
| `enforcement.log_every_block` | false | append every block to `.delivery/blocks.log`: time, hook (`stop`/`pre-tool`), rule id, message (tab separated) |
| `watcher.push_trains` | true | push the next joined train |
| `watcher.open_prs` | true | open its ready PR; the body carries `.delivery/docs-summaries.md` (written by `join.py`) when present |
| `watcher.merge_on_green` | true | `gh pr merge N --merge --match-head-commit SHA`, never `--auto`, only when the head is unchanged since the green run |
| `watcher.manage_runners` | true | launch `runner_plan.py runners` on the loop (needs `runners[]`; D6a) |
| `runner_plan.cancel_replaced_runs` | true | cancel CI runs of a head a newer push replaced |
| `runner_plan.hold_dependabot_during_train` | true | cancel, then re-run, non-train CI runs while a train's CI runs |
| `runner_plan.heavy_jobs_yield` | true | `runner_plan.py run` waits for train CI (`heavy_local_jobs_yield` is accepted too) |

Accepted alternative spellings: `watcher.merge_method: "merge"` or `merge_flag: "--merge"` (plus `never_auto_merge: true`) and `heavy_local_jobs_yield`. The plugin's earlier names (`caps`, `runners[]`, `runner_plan.retry_seconds`, `watcher_interval_s`, ...) are unchanged.

**Recording the smoke and the cleanup (DL-14, DL-18).** The Stop hook reads `cleaned_at` and `smoke.state` of the train row, which only the ledger writes. Project scripts (`cleanup.py`, `delivery_log.py live`) may not, so the plugin has its own commands; the DL-14 and DL-18 messages name the project's configured command, then these:

```
python <plugin>/scripts/delivery_ledger.py smoke --pr N [--run <id|url>]
python <plugin>/scripts/delivery_ledger.py cleaned --pr N
```

**Recording an agent's ETA (DL-30).** An agent launched without an ETA breakdown makes the Stop hook block. Record it with `python <plugin>/scripts/delivery_ledger.py agent-eta <agent id or task> --setup N --work N --checks N [--basis TEXT] [--root R]`. It sets the running agent's `eta` (total, breakdown, basis, due = started + total) under the ledger lock, prints it, and exits 1 when no running agent matches. The `delivery` block may also carry the one-line form `eta: setup 5 + work 60 + checks 10 = 75 min`; separate `setup:`, `work:`, `checks:` lines win when both exist.

`smoke` uses `gh` to find the newest `Production smoke` run (`smoke_workflow`) on the PR's merge commit (or the run you pass): success records `smoke {state: pass, at, run}` and `live_at` on every row with that `pr`; a failed run records `fail` and exits 1; a missing or unfinished run records nothing and exits 1. `cleaned` checks with `git ls-remote` that the train's branch and its cargo branches are gone from `origin` and with `git worktree list` that no worktree holds them, then records `cleaned_at` on every row with that `pr`; otherwise it lists what is left and records nothing. Both write through the ledger lock, touch only those fields and add an event. CI fields are never touched.

**Loop limit (`stop_repeat_limit`).** `.delivery/hook-state.json` keeps, per session, each finding's key plus the ledger fields it depends on (the train's or agent's row). The same unchanged finding blocks that many turn ends (3), then the next turn ends are not blocked for it: one notice per session says it is still open and names the command. A change to those fields, or a new finding, starts again. It matters for findings that only the owner or an outside step can clear: DL-14, DL-18, DL-03, DL-02, DL-76 and DL-63. Findings you can clear by acting now (DL-33 watcher heartbeat, DL-30 and DL-32 agent checks, DL-31 and DL-64 wording, Q-2) are limited the same way, but each rewrite or fix changes the finding, so they keep blocking as before.

**Questions (Q-5).** `AskUserQuestion` is denied when this session's agents are still running and a question batch was already asked within `question_window_min` (default 60) since the owner's last prompt: park the question until the wave reports, then ask everything at once. Allowed when every running agent has `blocked_on: "owner"`, when the owner's latest prompt asked for questions ("ask me questions"), or for dialogs issued within `question_batch_sec` (default 90) of the previous one (several dialogs in one message, Q-1). `checks_off: ["Q-5"]` switches it off.

`tz` must load through zoneinfo. Where tzdata is missing (Windows: `pip install tzdata`) the validator and the doctor fail, and the ledger warns on stderr instead of quietly using UTC.

## 0.3.0 (folded on the release branch)

- **DL-31** no longer flags measured durations (`took`, `saves`, `costs`, `each`...), a sentence listing two or more durations, or a sentence whose bullet already carries a clock time or the dependency. `ready in about 5 minutes` and `takes about 1 hour` about future work are still flagged.
- **DL-03** a train is green only when every workflow in `watcher.ci_workflows` (default `["ci.yml"]`) completed with `success` on the PR head commit. `ci_watch.py` passing no longer sets green; the watcher does, and revokes green when a required run is running again.
- **DL-76** one CI per release. `pr_proven_jobs` in `.delivery/config.json` lists the job names the release PR proves (globs ok), e.g. `["Windows tests", "test-*"]`. After the merge the Stop hook finds the PR's merge commit, and when its tree equals the PR head tree it flags every such job that ran on the default branch. Rule: "A release runs CI once: nothing after the merge re-runs what the release PR proved on the same tree; only publish, deploy and production smoke run on the default branch." Off while `pr_proven_jobs` is empty.

## Branch gate order (DL-84) and runner split (DL-85)

The branch gate runs the always-on guards, then typecheck + lint of the touched packages and their dependents, then the test steps; a time limit never skips lint or types, `gate_verify.py` refuses a result where they did not run, and the generated pre-push hook runs them too. On one shared Linux runner, OS-neutral CI jobs (lint, types, boundaries, portable contract/unit tests) should run on another available runner in parallel.

## CI-gate path (opt-in, DL-80..83)

For a project whose agents are gated by CI on their branch instead of a full local gate. Nothing changes for a project that does not opt in. The scripts live in `luismc-project-setup` (`tooling/shared/scripts/delivery/`) and the project's patterns in `scripts/delivery/ci-scope.json`; this plugin carries the rules, the spec and the brief:

- **Agents** run the tests of what they touch and the fast guards, push, and write a `CODE DONE` line in their report. `agent_ci.py` merges the branch onto its base (`--base`, default `origin/master`; a release branch while a train is open) into a two-parent commit on `ci/<task>` and starts one `workflow_dispatch` CI run per branch head; that run is the gate. A conflict is reported by file and starts nothing; `cleanup.py --pr N` removes the `ci/<task>` refs. The manual run plans `origin/<default>...HEAD`.
- **Caps** (DL-38): defaults cloud 20, local 3, total 23; a project's `.delivery/config.json` `caps` overrides them.
- **Orchestrator** joins urgent work at code push (`join.py --ci-gate`) and sizes ETAs from coding time plus the branch CI run. A CI plan script that a helper imports has no top-level `await`.
- **CI scope** (`ci_scope.py`): release PR full; CI files only, the CI tests and a named smoke set; root configuration full; else affected.
- **Run times**: the last job writes the artifact `ci-run-times` (repository variable `CI_RUN_TIMES=true`).
- **Brief**: `references/agent-brief-template.md`; `brief_markers` entries may be lists (`["one affected gate", "CI is the gate"]`).

## Tests

```
python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests
python3 -I tools/test_delivery_hooks.py
```

`tests/test_load.py` covers the load guard (parsers per OS, cache, limits precedence, heavy/light/cloud table, refusal, fail-open, notices, runner gate, doctor).
