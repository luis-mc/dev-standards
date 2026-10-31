# DS70: runner plan and Full Progress hourly/on-change publishing

Branch `DS70-runner-plan-hourly` (from `DS67-delivery-integration`). Contract: `docs/specs/delivery/DELIVERYSPEC.md` section 4 (c), decisions D2 and D6.

## Changes
1. `tech-stack-setup/.../scripts/delivery/runner_plan.py` (new): `runner_plan.py run --label NAME -- <cmd>`.
   - Waits while a release/train CI run (head branch matching `train_branch_regex`, default `^release/`) is queued, in progress or waiting; logs `runner_plan: waiting for CI <run id> (...)` every minute.
   - One heavy job at a time (`.delivery/runner-plan.lock`; a dead owner's lock is taken over), free-memory floor `min_free_mb`, optional pause of the local runner service (`sc` on Windows, `systemctl` elsewhere) that is ALWAYS resumed (`finally`, `atexit`, SIGINT/SIGTERM/SIGBREAK, which also stop the child). Optional CPU affinity and priority (Windows via ctypes, Linux via `sched_setaffinity`/`setpriority`).
   - Settings: `runner_plan` in `.delivery/config.json`, overridden by options. Exit: the command's code; 2 usage; 4 gave up (`max_wait_minutes`); 130 interrupted.
   - Ledger: best-effort `record("job"|"runner", data, root=...)` on the delivery plugin's `delivery_ledger.py` (found via `DELIVERY_LEDGER`, a sibling file, or `claude/plugins/delivery/scripts/`); no-op when absent or failing. The module does not exist yet on this branch: the call signature is a proposal the ledger agent must match (`jobs[]` fields per DELIVERYSPEC section 2; `runner` = name, paused_by, checked_at).
   - gh failure never blocks (warns once). Without a train-label filter on the runner's jobs, any train run counts (conservative).
   - Test: `tools/test_delivery_runner.py` (13 scenarios: fake clock/gh/memory/service/process table, plus two real subprocess runs with a stub `gh` and a real SIGTERM). New `delivery-runner` job in `spec-lint.yml`; listed in `CONTRACT.md` and the tooling README.
2. Artifacts plugin (change note `docs/specs/changes/DS70-hourly-publish.md`, spec and plugin both **minor**: the fold will give ARTIFACTSPEC 1.11.0 / luismc-artifacts 1.11.0; versions are not edited by hand, per the repo's convention):
   - R8.18 `hook_end_of_turn.py` blocks when Full Progress was published over 60 minutes ago, or a release task's `changed` stamp is later than `published_at`. Only after a first publish; not when `pending` already lists it; the 3-block ceiling applies.
   - R9.11 `pending --json` adds `copy_sha256` and `copy_written_at` and keeps them (plus a hash of the record files) in `.claude/artifacts-publish/<file>.meta.json`; `mark-published` refuses an edited copy or one older than the latest registry/content/design/page change (DL-62). The manifest and README are deliberately ignored (mark-deferred writes them). Content hash, not mtimes, so same-byte rewrites are no change.
   - R6.14/R8.19 `check` warns (not a finding, so writes are never refused) and the hook blocks on open rows whose Expected is past (`DD Mon` ends 23:59; zone from the manifest).
   - R9.8/R9.10 `pending --refresh` and new `scripts/publish_hourly.py` (silent under 60 minutes with no release change; otherwise the three steps).
   - Shared helpers in `scripts/artifact_hourly.py`; `artifactspec.md` gains R6.14, R8.18, R8.19, R9.8 to R9.11, a section 3.1 row, section 7 and 14 entries.
   - Tests: 4 hook cases in `tools/test_project_artifacts_hooks.py`; 5 cases in `tools/test_project_artifacts.py`; the key-list assertion of `test_pending_and_mark_published` updated.

## Checks run
- `tools/test_delivery_runner.py`: all passed.
- `tools/spec_check.py`: 0 errors. `change_notes.py check`: ok.
- Hook suite: full baseline 88 passed before my test additions; afterwards only the 4 new cases, by name (the full hook suite cannot be named-case run).
- `test_project_artifacts.py`: 31 cases touching `pending`/`mark-published` pass by name (`run_suite.py project-artifacts ...`); the new cases pass.
- Not run locally (session_guard refuses heavy suites; left to CI): `test_ci_areas.py`, `test_rule_tags.py`. I did add a `test_delivery_runner.py` row to `test_ci_areas.py`.
- Process note: before the guard was noticed, one full run of the hook suite (88 pass) and of the artifacts suite (105 pass, 3 failing from the new refusal and the key list, since fixed) went through a background compound command; no further full runs.

## Open
- The hook's fixture for the 60-minute and release checks relies on `published_at` in the manifest; a project that never ran `mark-published` is not nagged hourly.
- The rule file `rules/project-artifacts.md` is unchanged (its shipped-hash list, R10.6, would need regenerating); the hook reasons carry the instructions.
