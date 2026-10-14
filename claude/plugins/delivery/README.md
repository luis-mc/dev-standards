# luismc-delivery

Delivery guard rails for a project that opts in with a `.delivery/` folder. Rules: `docs/specs/delivery/DELIVERYSPEC.md`. Without `.delivery/` the hooks do nothing.

| Script | What it does |
|---|---|
| `hook_*.py` | Stop, PreToolUse, PostToolUse, SessionStart hooks (registered by `hooks/hooks.json`) |
| `delivery_ledger.py` | the ledger `.delivery/ledger.json` |
| `delivery_watch.py` | background watcher: pushes the next train, opens its PR, merges at green, tidies CI runs, keeps the runner guard running |
| `delivery_config.py validate` | checks `.delivery/config.json` against `references/config-schema.json` |
| `delivery_doctor.py` | self-check: config valid, gh signed in, tz loads, hooks registered, ledger writable |

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
| `enforcement.mode` | `block` | `warn` shows findings and denials as a message and blocks nothing |
| `enforcement.block_ceiling` | 3 | the same findings block a session this many times, then the turn ends |
| `enforcement.log_every_block` | false | append every block to `.delivery/blocks.log`: time, hook (`stop`/`pre-tool`), rule id, message (tab separated) |
| `watcher.push_trains` | true | push the next joined train |
| `watcher.open_prs` | true | open its ready PR |
| `watcher.merge_on_green` | true | `gh pr merge N --merge --match-head-commit SHA`, never `--auto`, only when the head is unchanged since the green run |
| `watcher.manage_runners` | true | launch `runner_plan.py runners` on the loop (needs `runners[]`; D6a) |
| `runner_plan.cancel_replaced_runs` | true | cancel CI runs of a head a newer push replaced |
| `runner_plan.hold_dependabot_during_train` | true | cancel, then re-run, non-train CI runs while a train's CI runs |
| `runner_plan.heavy_jobs_yield` | true | `runner_plan.py run` waits for train CI (`heavy_local_jobs_yield` is accepted too) |

Accepted spellings from the comics-organizer config: `watcher.merge_method: "merge"` or `merge_flag: "--merge"` (plus `never_auto_merge: true`) and `heavy_local_jobs_yield`. The plugin's earlier names (`caps`, `runners[]`, `runner_plan.retry_seconds`, `watcher_interval_s`, ...) are unchanged.

`tz` must load through zoneinfo. Where tzdata is missing (Windows: `pip install tzdata`) the validator and the doctor fail, and the ledger warns on stderr instead of quietly using UTC.

## Tests

```
python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests
python3 -I tools/test_delivery_hooks.py
```
