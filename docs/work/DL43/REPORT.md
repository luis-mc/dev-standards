# DL43 / DL46 report

Files: delivery_watch.py (pr_workflows, skipped = success, required set), hook_stop.py (PAST_RE / FUTURE_RE in is_measured), tests test_watch.py and test_stop.py, DELIVERYSPEC.md (DL-31, DL-03 wording), change note.
Decisions: green is set only by the watcher; the required set is the configured list plus every pull_request workflow file. With no configured list, found PR workflows replace the `ci.yml` default. A past-tense sentence with no future cue is not an ETA. A sentence with both ("started 1 min ago, ready in 6 min") with two durations is still read as measured (old rule, unchanged).
Not changed: the ledger `ci` record op still trusts the caller's state; nothing in the repo calls it for green.
Ran: delivery suite 576 tests OK. tools/test_delivery_hooks.py not run: session guard refuses the heavy suite locally; CI advice: gh workflow run spec-lint.yml --ref DL43-eta-and-green -f areas=delivery.
