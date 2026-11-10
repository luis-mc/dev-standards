# DL171 report

## What changed
- `hook_pre_tool.py`: DL-42 now runs per command segment, only when the program stops or kills (docker stop/kill/rm, docker compose down/stop/kill/rm, kill, taskkill, pkill, Stop-Process). `xargs docker stop` after a `docker ps` stays blocked. `$(docker ps ...)` inside docker exec/logs/inspect/cp is allowed.
- `hooklib.py`: `record_dir(root)`: docs/docs.json `record_dir`, then .claude/artifacts.json `record_dir`, default docs/project. `hook_stop.py check_registry` uses it and falls back to docs/artifacts when the resolved registry is missing (older projects, existing tests).
- `hook_stop.py` Q-2: ignores `?` in code spans, block quotes, quoted text, and a closing "no question for you" line.
- `questions_stop.py`: plain-text question detection removed; parking (Q-1, Q-5) kept.
- Tests: new `test_dl171_hook_rules.py`; `tools/test_questions_stop.py` updated.
- Notes: two change notes in `docs/architecture/changes/`, one feature note `docs/features/delivery/changes/DL171.md`.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl171_hook_rules test_pre_tool test_stop`: 71 tests OK
- `python3 tools/test_questions_stop.py`: 0 problems (the session guard required `run_suite.py --measure questions-stop` once; it recorded 1.0s in the ignored .delivery/suite-times.json)
- `run_suite.py --measure delivery-hooks` (tools/test_delivery_hooks.py): 55 passed, 0 failed

## docs_check
- G1 (decisions.md stale): generated file, not mine; the release fold rebuilds it.
- M1 (project-setup spec): `questions_stop.py` changed; the project-setup feature spec is not in my owns list, so the commit says `Docs: none` and the plugin change note carries it. Orchestrator may add a project-setup feature note.
