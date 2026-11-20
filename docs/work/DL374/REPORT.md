# DL374 report

Files: hook_pre_tool.py (DL-97), cancel_joined_runs.py (--blocks-all), delivery_doctor.py (DL-98), agents-and-integration.md (3 rule lines), DELIVERYSPEC 1a (DL-97, DL-98), delivery-speed spec R5.18/R5.19, change notes, tests/test_dl374_red_run_finishes.py.
Templates: the only matrix (ts ci.yml e2e-shard) already sets fail-fast: false; no template passes a stop flag. No template change needed.

Tests (cd claude/plugins/delivery/tests; python3 -m unittest <name>):
- test_dl374_red_run_finishes: OK (12)
- test_pre_tool, test_dl171_hook_rules, test_doctor, test_dl188_doctor_tools, test_dl113_cancel_joined, test_dl235_ci_watch_quota: OK

docs_check: 1 error, G1 docs/architecture/decisions.md stale. It is generated, and it is stale on origin/main too (contract commit 40bc84d). Not committed here. No other errors.

Branch head: code commit f81bb8b (report commit follows).

READY
