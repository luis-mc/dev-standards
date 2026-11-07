# DL96 report (DL96, DL97, DL98, DL100)

## What changed
- **DL96 (D115)** `delivery_ledger.py`: `agent_ids`, `link_run_id`, `find_agent`; `merge_agent_rows` now also merges by a shared id (`trigger_id`, `run_ids`) and migrates `alt_ids` to `run_ids`. `load()` merges on read; `hooklib.load_ledger` does too, so DL-30 asks once. `hook_post_tool.rec_agent` links a cse_ run of an open known trig_ launch instead of adding a row. `agent-eta` and `agent-done` take either id.
- **DL97 (D112)** `hook_stop.py`: "~HH:MM if <action> by HH:MM" counts as a named dependency. More past verbs (used, held, needed, peaked...) mark a past duration as a fact. The refusal message lists the accepted forms.
- **DL98 (D116)** `delivery_watch.py` stamps `version` on its watcher row (read once at start). `hook_session_start.py` stops a watcher whose version is older or missing, by recorded pid only (refuses own pid, pid <= 1, or a process whose cmdline is readable and is not delivery_watch), then starts the installed watcher.
- **DL100 (D114)** `hook_pre_tool.py` new rule **DL-93**: a cloud create needs `clear_mcp_connections: true` or a non-empty `mcp_connections`. Template and `docs/guides/cloud-routines.md` updated.
- Docs: DELIVERYSPEC rows DL-30, DL-31, DL-33, new DL-93, watcher example; feature spec R5.15-R5.18; two change notes; four feature notes (`docs/features/delivery/changes/DL96,DL97,DL98,DL100.md`).

## Files outside the owned list (needed, please review)
- `claude/plugins/delivery/tests/test_pre_tool.py`: two create fixtures gained `clear_mcp_connections: True`.
- `tools/test_delivery_hooks.py`: create fixtures gained the field, one DL-93 proof case added (CI "Prove the delivery hooks" job failed without this).
- `rules/` has no DL-31 text; nothing changed there. README.md not touched (not owned).

## Tests
- `python3 -m unittest test_dl96_ledger_ids test_dl96_eta_forms test_dl96_watcher_rearm test_dl96_cloud_create`: 25 ok.
- Same plus test_ledger test_stop test_watch test_pre_tool test_post_tool test_recording test_brief_template test_questions test_doctor: 334 ok.
- `gh workflow run spec-lint.yml --ref DL96-ledger-hooks-launch -f areas=delivery`, watched with ci_watch.py. Run 42320512522 on e215302: every delivery job passed. Only `docs check` failed, with the expected G1 (stale decisions.md) and W1 (docs/work). The first run (16a833b) had failed on the hook proof; fixed in e215302.
- `docs_check.py`: G1, W1 (expected), 3 warnings (M1 template not mapped, T2 x2).
- tools/test_rule_tags.py not run locally (heavy, refused by the guard); CI covered it.

Branch head: see `git rev-parse HEAD` on origin/DL96-ledger-hooks-launch (the commit that adds this report).

READY
