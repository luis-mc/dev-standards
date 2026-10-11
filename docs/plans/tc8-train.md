# TC8 train: generic CI speed for products

Integration branch `TC8-integration`; one agent branch `TC8-ci-speed-generic`. Runs beside the AR43 train (which owns `claude/plugins/artifacts/**` and the artifacts tests); the two never touch the same file. Owner decisions: test-cost D12 ("Generic SHOULD, next train") and D13 ("Start now, in parallel").

Evidence (dev-standards, TC7): one serial job was 11.4 of 11.6 minutes; splitting it per suite and sharding its slowest part brought the PR run to 3.0 minutes. Products have no mutation pass, so the generic form is about the job that dominates.

| Branch | Owns |
|---|---|
| `TC8-ci-speed-generic` | STACKSPEC `invariants.md` (§13.1 CI paragraph and the conformance checklist line), the four tracks' `ci.yml`, `shared/scripts/delivery/ci_watch.py` and its `CONTRACT.md` paragraph, `tools/test_delivery_ci.py`, `tools/template_build_check.py` if it validates the templates, tech-stack-setup `SKILL.md` (one paragraph), one change note |

1. **STACKSPEC SHOULD (§13.1).** CI wall time is set by its slowest job. A job or step that takes most of a run SHOULD get its own job, and a test step that can be split SHOULD run as parallel shards; small steps stay together, because every job repeats setup. Projects find the dominant job from ci_watch's summary (item 3). Add it to the conformance checklist as a SHOULD.
2. **e2e shards in the templates.** In each track's `ci.yml` whose e2e job runs Playwright (today: ts), the e2e job becomes a matrix of shards (`--shard=${{ matrix.shard }}/${{ strategy.job-total }}` or equivalent), default 2 shards set in one place, with `fail-fast: false`. Keep any required-check name working (a small summary job with the old name that needs the shards, as TC7 did). Tracks without Playwright e2e: no change; say so in the report.
3. **ci_watch slowest-job summary.** When all watched runs are complete, `ci_watch.py` prints one summary: each run's wall time, its slowest job, and that job's share of the run and its two slowest steps (from `gh run view --json jobs`). It never changes the exit code, and on any error it prints nothing extra. Add cases to `tools/test_delivery_ci.py` with the existing gh stub.
4. **Versions.** Change note `docs/specs/changes/TC8-ci-speed-generic.md` with `spec:` invariants.md and `plugin:` the luismc-project-setup `plugin.json`, `change: minor`. Never edit version lines or change logs.
5. **Testing.** Light change: run locally `python -I tools/test_delivery_ci.py --no-mutants` (or without the flag if it has none) and the template check if you changed what it reads. No Docker, no CI runs, no full gate suite. Never kill processes by name; stop only what you started, by PID.
