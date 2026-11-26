# DL429 report: status badges and "What is happening"

Branch: `DL429-status-badges` (from origin/main 576d6239).

## What changed

- `render_artifacts.py`: Full Progress section 0 now holds the stamp, a full-width badge row (`div.status-badges`), a generated `div.what-happens` list (at most 8 bullets), the status key and the checklist. The At a glance block, the count tiles and the lede are gone from Full Progress; feature artifacts keep them. `check_html` knows the new order and finds a leftover glance, lede or tiles (R5.61), wrong count badges (R5.61), and an empty, long or train-labelled bullet list (R5.62).
- `ledger_links.py`: new read-only `read()` returns the trains by release and the agents.
- `project-artifact.css`: badge and bullet styles, tokens only.
- Spec: R5.61 to R5.63 in `claude/plugins/docs/references/artifactspec.md`; R5.31 to R5.33 in `docs/features/artifacts/spec.md`. Notes: plugin, spec, `features/artifacts`, `features/docs`. Generated docs rebuilt with `docs_index.py build`.
- New tests: `tools/test_artifacts_dl429.py` (11 cases), declared in `.claude/suites.json` and `.github/workflows/spec-lint.yml`.
- Skill text: `full-progress-artifact-new/SKILL.md` no longer says the lede is shown.

## Existing tests updated (they named the removed lines)

All in `tools/test_render_artifacts.py`. A new helper `own_registry` / `feature_view` renders a feature artifact that owns every task, so the glance rules are still proved on the kind that keeps them.
`needs_you_sentence`, `tiles_count_each_status_in_order_and_skip_empty`, `glance_groups_are_collapsible_details`, `check_finds_a_wrong_glance_state`, `check_r57_lede`, `at_a_glance_groups_and_order`, `glance_splits_owner_waits_from_work_waits`, `glance_default_waits_on_work_keeps_old_grouping`, `glance_needs_you_count_matches_the_section`, `check_finds_a_wrong_split_or_dependency`, `check_r534_each_group_lists_its_tasks`, `tiles_say_tasks`, `release_group_heading_with_risk`, `dropped_release_is_closed_history`.

## Test results (local, light)

- `artifacts-dl429`: 11 passed. `artifacts-ds256`, `-dl251`, `-dl246`, `-dl259`, `-dl260`, `-dl264`, `-ar59`, `-ar60`, `-ar63`, `-ar66`, `-ar67`, `-dl173`, `-dl269`, `-dp7`, `-ds219`: all passed.
- `test_render_artifacts.py`: only the named cases that touch glance, tiles or lede (26 cases) were run; all pass after the updates. The full run is left to CI.
- `artifacts-dl238` `writes_to_local_dir` fails, but it fails the same way on a clean origin/main checkout (a Windows-only difference between the local and publish copies); not caused by this change.
- `docs_check.py`: one M1 error for `.github/workflows/spec-lint.yml` (test-cost spec), cleared by the `Docs: none` line in the commit message; the rest are old T2 warnings.

## Notes

- The ledger has no carrier PR for a release that has no train; the badge and bullet then omit the PR.
- The CI badge counts the runs of the active releases and the last Live release; with no run mapped it counts the whole file.
- `check_html` does not read `ci-runs.json`, so it still reports the CI runs section as missing when a test passes runs to the render (existing behaviour, R5.51).
- No e2e specs exist for the generated page; render tests are the proof.
