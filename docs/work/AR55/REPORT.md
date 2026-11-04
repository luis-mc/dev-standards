# AR55 report

Bug: `set-task-status` refused a release when Expected differed from the end of its last phase, even if the call gave no `--expected`.

Files changed:
- claude/plugins/artifacts/scripts/project_artifacts.py (new `phase_expected`; `apply_release_fields` takes `expected_given`; `task-add --expected` optional for an open `--release` with `--phase`)
- tools/test_project_artifacts.py (the R5.41 case now covers phase-only, midnight roll, basis-only, explicit contradiction naming the right value, task-add)
- claude/plugins/artifacts/references/artifactspec.md (R5.41 wording)
- docs/features/artifacts/spec.md (R5.11), docs/features/artifacts/changes/AR55.md
- docs/architecture/changes/AR55-expected-from-phase.md (patch)

Decisions: a `; note` after Expected is kept when Expected is re-derived. Only open statuses are re-derived. Omitting `--expected` on `task-add` is allowed only for an open `--release` with `--phase`.

Ran:
- run_suite.py project-artifacts, cases test_release_expected_is_the_end_of_the_last_phase, test_release_flags_store_the_fields, test_release_refusals: all pass.
- docs_check.py: 0 errors, 1 warning (T2 on test-cost spec, not my file).
- Full suite not run locally (guard); CI advice: `gh workflow run spec-lint.yml --ref AR55-expected-from-phase -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`.

READY
