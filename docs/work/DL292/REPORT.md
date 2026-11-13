# DL292 report

Base check: queue_list on origin/main had the same-host pid check line. OK.

## What changed
- machine_slots.py: enqueue writes beat_ts; new beat() rewrites the ticket atomically under the same name; queue_list drops any-host tickets with no beat for max(4 x poll_sec, 120 s) and logs reason `no heartbeat` with host, job, repo.
- runner_load_gate.py: queue_wait beats each poll; the re-enqueue path keeps queued_ts and gives a fresh beat_ts.
- New tests: claude/plugins/delivery/tests/test_dl292_ticket_heartbeat.py.
- Docs: shared-self-hosted-runners.md 3.2, feature note, architecture change note.

## Tests
- python3 -m unittest test_dl292_ticket_heartbeat test_machine test_dl200_gate_vanished_ticket test_dl267_light_slot test_dl270_light_slot_listing: 94 OK
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- docs_check: M1 on runner-pool/spec.md answered with `Docs: none` in the commit; W1 on docs/work expected.
- spec-lint workflow: not run (no gh workflow access in this environment; see follow-ups).

## Follow-ups
- Dispatch spec-lint.yml for DL292-ticket-heartbeat with areas=delivery.

Branch head SHA: see last commit on DL292-ticket-heartbeat.
READY
