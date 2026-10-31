# DS87 report: ci_watch exits 2 at once on a missing workflow

Branch `DS87-ci-watch-missing-workflow`.

## Plan
- ci_watch.py: a `gh run list` failure that is the 404 "workflow ... not found" is not retried: exit 2 at once, naming the workflow and listing the repository's workflows (`gh workflow list --all --json name,path`, best effort). Other gh errors keep the 5-try retry.
- Docstring and `--workflow` help say so.
- tools/test_delivery_ci.py: stub gh learns `workflow list`; three new tests.
- Change note docs/specs/changes/DS87-ci-watch-missing-workflow.md (plugin patch).
- ci_watch.py exists in one place only in the repo, so there are no copies to keep identical.

## Done
Files changed:
- claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/ci_watch.py (WorkflowNotFound, narrow match, workflow listing, docstring, --workflow help)
- tools/test_delivery_ci.py (stub gh answers `workflow list`; 3 new tests)
- docs/specs/changes/DS87-ci-watch-missing-workflow.md (plugin patch)
- docs/agents/reports/DS87-report.md

Tests: `python tools/test_delivery_ci.py` is refused locally by the session guard (heavy suite, measure=false), and run_suite.py has no named-case support for it. I ran every `watch_*` test function directly: 32 passed (the 33rd match, `watch_queued`, is a helper), including the three new ones and the existing retry/give-up tests. The full suite is left to CI.

Open: nothing. ci_watch.py has no copies elsewhere in the repo.
