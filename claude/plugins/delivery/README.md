# luismc-delivery

Delivery guard rails for a project that opts in with a `.delivery/` folder. Rules: `docs/architecture/DELIVERYSPEC.md`. Without `.delivery/` the delivery hooks do nothing.

| Script | What it does |
|---|---|
| `hook_*.py` | Stop, PreToolUse, PostToolUse, SessionStart hooks (registered by `hooks/hooks.json`) |
| `delivery_ledger.py` | the ledger `.delivery/ledger.json` |
| `delivery_watch.py` | background watcher: pushes the next train, opens its PR (or adopts the one open PR of a train pushed by hand), merges at green, tidies CI runs |
| `rules/clarifying-questions.md` | the canonical question rules (Q-1..Q-5); SessionStart injects them every session |
| `delivery_config.py validate` | checks `.delivery/config.json` against `references/config-schema.json` |
| `delivery_doctor.py` | self-check: config valid, gh signed in, tz loads, hooks registered, ledger writable |

## Machine limits

The plugin no longer owns machine limits, runner hooks or CI slots. Another project owns them. The plugin keeps tasks, trains, when a CI run starts, how finished CI is detected, merge, the watcher and the Stop hook.

## `.delivery/config.json`

Every key is optional. Defaults reproduce 0.1.0. Unknown keys warn. `_` keys are comments. Check it with

```
python3 scripts/delivery_config.py validate --root .      # exit 0 valid, 1 errors, 2 unreadable
python3 scripts/delivery_doctor.py                        # exit 0 all ok
```

New in 0.2.0:

```json
{
  "tz": "Europe/Lisbon",
  "enforcement": { "mode": "block", "block_ceiling": 3, "log_every_block": true },
  "watcher": { "push_trains": true, "open_prs": true, "merge_on_green": true },
  "runner_plan": { "cancel_replaced_runs": true, "hold_dependabot_during_train": true }
}
```

| Key | Default | Effect |
|---|---|---|
| `enforcement.mode` | `block` | `warn` shows findings and denials as a message and blocks nothing |
| `enforcement.block_ceiling` | 3 | the same findings block a session this many times, then the turn ends |
| `stop_repeat_limit` | `block_ceiling` | the Stop hook stops blocking a finding after it blocked this many turn ends in a row with no change to the ledger fields it depends on; 0 = never limit |
| `cleanup_command`, `smoke_command` | unset | the project's commands (`{pr}` = PR number) that the DL-14 and DL-18 messages name before the recording command |
| `smoke_workflow` | `Production smoke` | the workflow `delivery_ledger.py smoke` looks for |
| `enforcement.log_every_block` | false | append every block to `.delivery/blocks.log`: time, hook (`stop`/`pre-tool`), rule id, message (tab separated) |
| `watcher.push_trains` | true | push the next joined train |
| `watcher.open_prs` | true | open its ready PR; the body carries `.delivery/docs-summaries.md` (written by `join.py`) when present |
| `watcher.merge_mode` | `auto` | `auto`: merge on green. `manual`: the owner merges; the watcher never merges and the hooks refuse an agent's `gh pr merge` (DP16) |
| `watcher.merge_on_green` | true | `gh pr merge N --merge --match-head-commit SHA`, never `--auto`, only when the head is unchanged since the green run |
| `deploy.serial` | false | releases deploy one after another; Full Progress then shows a release waiting on every earlier open release whose train merged first. A project with serial deploys sets it once |
| `runner_plan.cancel_replaced_runs` | true | cancel CI runs of a head a newer push replaced |
| `runner_plan.hold_dependabot_during_train` | true | cancel, then re-run, non-train CI runs while a train's CI runs |

Accepted alternative spellings: `watcher.merge_method: "merge"` or `merge_flag: "--merge"` (plus `never_auto_merge: true`). The plugin's earlier names (`caps`, `runners[]`, `runner_plan.retry_seconds`, `watcher_interval_s`, ...) are unchanged.

**Recording the smoke and the cleanup (DL-14, DL-18).** The Stop hook reads `cleaned_at` and `smoke.state` of the train row, which only the ledger writes. Project scripts (`cleanup.py`, `delivery_log.py live`) may not write them, so the plugin has its own commands. The DL-14 and DL-18 messages name the project's configured command, then these:

```
python <plugin>/scripts/delivery_ledger.py smoke --pr N [--run <id|url>]
python <plugin>/scripts/delivery_ledger.py cleaned --pr N
```

**Recording an agent's ETA (DL-30).** The Stop hook blocks when an agent was launched without an ETA breakdown. Record it with `python <plugin>/scripts/delivery_ledger.py agent-eta <agent id or task> --setup N --work N --checks N [--basis TEXT] [--root R]`. It takes any open agent (queued, running, pushed or stalled), by routine id, run session id or task, and sets its `eta` (total, breakdown, basis, due = started + total) under the ledger lock and prints it. `--root` works before or after the subcommand. It exits 1 when no open agent matches. One launch that left a routine row and a run session row is merged into one row. The `delivery` block may also carry the one-line form `eta: setup 5 + work 60 + checks 10 = 75 min`. Separate `setup:`, `work:`, `checks:` lines win when both exist.

`smoke` uses `gh` to find the newest `Production smoke` run (`smoke_workflow`) on the PR's merge commit (or the run you pass): success records `smoke {state: pass, at, run}` and `live_at` on every row with that `pr`; a failed run records `fail` and exits 1; a missing or unfinished run records nothing and exits 1. `cleaned` checks with `git ls-remote` that the train's branch and its cargo branches are gone from `origin` and with `git worktree list` that no worktree holds them, then records `cleaned_at` on every row with that `pr`; otherwise it lists what is left and records nothing. Both write through the ledger lock, touch only those fields and add an event. CI fields are never touched.

**Loop limit (`stop_repeat_limit`).** `.delivery/hook-state.json` keeps, per session, each finding's key plus the ledger fields it depends on (the train's or agent's row). The same unchanged finding blocks that many turn ends (3). After that, later turn ends are not blocked for it. One notice per session says it is still open and names the command. A change to those fields, or a new finding, starts the count again. It matters for findings that only the owner or an outside step can clear: DL-14, DL-18, DL-03, DL-02, DL-76 and DL-63. Findings you can clear by acting now (DL-33 watcher heartbeat, DL-30 and DL-32 agent checks, DL-31 and DL-64 wording, Q-2) are limited the same way, but each rewrite or fix changes the finding, so they keep blocking as before.

**Questions (Q-5).** `AskUserQuestion` is denied when this session's agents are still running and a question batch was already asked within `question_window_min` (default 60) since the owner's last prompt: park the question until the wave reports, then ask everything at once. Allowed when every running agent has `blocked_on: "owner"`, when the owner's latest prompt asked for questions ("ask me questions"), or for dialogs issued within `question_batch_sec` (default 90) of the previous one (several dialogs in one message, Q-1). `checks_off: ["Q-5"]` switches it off.

`tz` must load through zoneinfo. Where tzdata is missing (Windows: `pip install tzdata`), the validator and the doctor fail, and the ledger warns on stderr instead of quietly using UTC.

## 0.3.0 (folded on the release branch)

- **DL-31** no longer flags measured durations (`took`, `saves`, `costs`, `each`...), a sentence listing two or more durations, or a sentence whose bullet already carries a clock time or the dependency. `ready in about 5 minutes` and `takes about 1 hour` about future work are still flagged.
- **DL-03** a train is green only when every workflow in `watcher.ci_workflows` (default `["ci.yml"]`) completed with `success` on the PR head commit. `ci_watch.py` passing no longer sets green; the watcher does, and revokes green when a required run is running again.
- **DL-76** one CI per release. `pr_proven_jobs` in `.delivery/config.json` lists the job names the release PR proves (globs ok), e.g. `["Windows tests", "test-*"]`. After the merge the Stop hook finds the PR's merge commit, and when its tree equals the PR head tree it flags every such job that ran on the default branch. Rule: "A release runs CI once: nothing after the merge re-runs what the release PR proved on the same tree; only publish, deploy and production smoke run on the default branch." Off while `pr_proven_jobs` is empty.

## Branch gate order (DL-84) and runner split (DL-85)

The branch gate runs the always-on guards, then typecheck + lint of the touched packages and their dependents, then the test steps. A time limit never skips lint or types. `gate_verify.py` refuses a result where they did not run. The generated pre-push hook runs them too. On one shared Linux runner, OS-neutral CI jobs (lint, types, boundaries, portable contract/unit tests) should run on another available runner in parallel.

## CI-gate path (opt-in, DL-80..83)

For a project whose agents are gated by CI on their branch instead of a full local gate. Nothing changes for a project that does not opt in. The scripts live in this plugin (`templates/shared/scripts/delivery/`). The project's patterns live in `scripts/delivery/ci-scope.json`. This plugin carries the rules, the spec and the brief:

- **Agents** run the tests of what they touch and the fast guards, push, and write a `CODE DONE` line in their report. `agent_ci.py` merges the branch onto its base (`--base`, default `origin/master`; a release branch while a train is open) into a two-parent commit on `ci/<task>` and starts one `workflow_dispatch` CI run per branch head; that run is the gate. A conflict is reported by file and starts nothing; `cleanup.py --pr N` removes the `ci/<task>` refs. The manual run plans `origin/<default>...HEAD`.
- **Caps** (DL-38): defaults cloud 50, local 3, total 53; a project's `.delivery/config.json` `caps` overrides them.
- **Orchestrator** joins urgent work at code push (`join.py --ci-gate`) and sizes ETAs from coding time plus the branch CI run. A CI plan script that a helper imports has no top-level `await`.
- **CI scope** (`ci_scope.py`): release PR full; CI files only, the CI tests and a named smoke set; root configuration full; else affected.
- **Run times**: the last job writes the artifact `ci-run-times` (repository variable `CI_RUN_TIMES=true`).
- **E2E (DL-86..DL-89)**: an agent that changes UI code runs the e2e specs of the screens it changed (`scripts/delivery/branch_gate.py --e2e-only`) before CODE DONE. The gate records them, `gate_verify.py` and `agent_ci.py` refuse a UI branch without the record, the pre-push hook refuses an unrun e2e fix, and the launch check needs the brief line "run the e2e specs of the screens you change" (or "no UI change").
- **Brief**: `references/agent-brief-template.md`; `brief_markers` entries may be lists (`["one affected gate", "CI is the gate"]`).

## CI options (DL15)

CI can run in four ways (the owner's Option 1 to 4). The owner picks one for each OS (linux, windows, macos). Config values exist for Options 1 to 3; Option 4 is the `ci.fallback` block on an Option 1 OS. There is no default: `/delivery-ci-setup` asks every question and writes the config, and running it again changes the choice.

| Option | Config value | Runs on |
|---|---|---|
| 1 | `self-hosted` | GitHub Actions on your own self-hosted runners, on any machines you run |
| 2 | `github-hosted` | GitHub Actions on GitHub's runners |
| 3 | `cloud` | Claude cloud sessions (no Actions, no webhooks) |
| 4 | `self-hosted` plus `ci.fallback` | Own runners first, a fallback after X minutes of runner wait (`ci.fallback`: `options`, `after_min`, optional caps, `cloud`, `hosted`) |

0. Onboarding: in a project with no `.delivery/`, run `/delivery-onboard` (engine `scripts/delivery_onboard.py --merge-mode auto|manual`). It writes the config in warn mode, so nothing is blocked, and the ledger. It never overwrites a config.
1. Guided: run `/delivery-ci-setup` (engine `scripts/delivery_ci_setup.py`). It writes `ci.options`, `ci.fallback`, `ci.limits`, the runners and the files, and prints the by-hand list. By hand: ask the owner, per OS. Record it: `python3 scripts/delivery_ci.py set --os linux --option 1|2|3` (`show`, `unset` also exist). It writes `ci.options` in `.delivery/config.json`.
2. Write the CI and delivery files: `python3 scripts/delivery_ci_install.py install --track ts|go|rust|dotnet --root .` (`update` later). The files come from `templates/`. tech-stack-setup calls this at the end of its setup. The command never commits.
3. The product gives a shard table, `scripts/delivery/ci-shards.json` (format: `ci-shards.example.json`).
4. Option 1: list the runners in `runners`, one entry per machine. Option 3: set `ci.cloud.repo`, `ci.cloud.status_token_env` and `ci.cloud.branches`; the owner creates a statuses-only token and puts it in the cloud environment under that name.
5. `python3 scripts/delivery_doctor.py` reports the `ci` check. For Option 1 it names each machine it found and the by-hand steps to add another.

### Add a second runner (Option 1)

One runner of a label is the first bottleneck. A job that waits more than X minutes (the CI watch warns at 10) means: add a runner with the same label on another machine, any machine you run. A plugin cannot do it; it needs a person on that machine. Print the steps for that machine's OS:

```
python3 scripts/delivery_ci.py add-runner --os linux|windows|macos --labels self-hosted,linux
```

The steps: get the token on GitHub, unpack the runner, run `config.sh` (`config.cmd` on Windows) with the same labels, install it as a service, add the machine to `runners`, run the doctor.

Rules: `docs/features/delivery/spec.md` section 13. File formats: `templates/shared/scripts/delivery/CONTRACT.md`, "CI options".

## CI runs for Full Progress (DL31, D48)

`scripts/ci_runs.py collect --root .` writes `.delivery/ci-runs.json` (git-ignored). The artifacts plugin draws it as the `CI runs` section of Full Progress.

```
python3 scripts/ci_runs.py collect --root . [--repo owner/name] [--slot-log PATH]
```

- **Runs and steps** come from `gh api` (`actions/runs`, `actions/runs/{id}/jobs`). Finished runs are kept in the file, so only new runs cost a jobs call.
- **Why** is the trigger: ready PR, push to the default branch, agent branch, schedule, re-run, or a fallback with its wait.
- **Where** is the runner kind (`pool`, `windows`, `hosted`, `cloud`) and its name. For a cloud fallback the name is the holder of the `ci-claim` marker.
- **Slot wait** comes from the machine layer's `slot-log.jsonl` (the folder of `DELIVERY_MACHINE_DIR`, else the machine default). A missing log means a wait of 0.
- **Fallback in** uses `ci.fallback.after_min` in `.delivery/config.json`. Without it the file says the time is unknown.
- `delivery_watch.py` runs the collector each tick, at most once a minute. A failure leaves the old file and never fails the tick.
- Schema: `docs/features/delivery/shared-self-hosted-runners.md` section 12.5. One optional field is added to a finished run: `slot_start_s`, and `fallback: true` for a run that lost its claim.

Test: `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests -p "test_ci_runs.py"` (fixtures in `tests/fixtures/ci_runs/`).

## Tests

```
python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests
python3 -I tools/test_delivery_hooks.py
```


## Trust

`.delivery/config.json`, `gate.json` and `smoke.json` are code: they choose scripts and shell commands that run with your rights. Trust them only after review.
