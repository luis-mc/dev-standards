# DS278 report

Branch: `DS278-phases-required`. Two commits: the spec first, then the code.

## Built

- `set-task-status` exits 1 when a task moves to Running or Waiting and its release (its own, or the one it rides) has no phases. The message says to give `--phase agents=HH:MM-HH:MM` and the other phases. To do, Built, Live, Dropped and `--no-release` tasks are exempt.
- `--no-phases REASON` stores `no_phases` on the release. Only with Running or Waiting. An empty or one-word reason is refused, as is a reason over 80 characters or one given for a release that already has phases. Giving phases later removes the reason.
- `check` reports R5.41a for a Running or Waiting release with no phases and no reason. A row last changed before 26 Nov 2026 gives a warning instead. `docs/project` has no such row: `check` shows no R5.41a finding there.
- Page: an outline diamond (class `rt-expected rt-nophase`, inline style, so the stylesheet and every rendered page stay byte-identical), `live ~HH:MM · no phases` on the timeline, `<time> · no phases` in the Live ETA cell and `no phases: <reason>` in the Item cell of the release table. Legends updated.
- Spec: R5.41a, R5.42c, decision D26 in ARTIFACTSPEC; R5.37, R5.38 and a decision row in the feature spec; change notes for `features/artifacts`, `features/docs` and the docs `plugin.json`.

## Existing tests changed

- `tools/test_project_artifacts.py`: 4 places (the baseline fixture release DS1 now gets a reason, 2 calls; 3 release tests pass `--no-phases`). Counting only the lines changed: 4 edits, 26 cases that failed before now pass.
- `tools/test_render_artifacts.py`: 2 cases (`timeline_without_phases_is_a_diamond_at_expected`, `check_finds_a_timed_release_in_a_day_slot`).
- New `tools/test_artifacts_ds278.py` (8 cases), in `.claude/suites.json` and `spec-lint.yml`.

## Not verified

- No full suite ran. Ran: 8 new cases; the 33 `test_project_artifacts.py` cases that call `set-task-status`; 21 render cases (timeline, release); `test_artifacts_dp7`, `dl246`, `ar63`, `dl429`, `ds256`, `ds258`.
- `test_artifacts_dl238` fails one case (`writes_to_local_dir`) with and without this change.
- `task-add --status Running` is not refused (the task names `set-task-status`); `check` catches a release made that way.
- `docs_check` reports G1 (`docs/docs-map.json` stale, because the feature spec `code:` list gained the new test). The release regenerates it; the branch does not commit generated files.
- `check` on `docs/project` shows INV-3 on Full Progress, which it also shows on `main`.
