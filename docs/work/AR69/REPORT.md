# AR69 report: lighter Full Progress page

Base check: `origin/main` renderer has `EARLIER_DAYS` (14). Branch `AR69-lighter-full-progress` cut from `origin/main`.

## What changed per decision

- **D25 slim registry.** `registry_window()` keeps every task not Live or Dropped, plus Live and Dropped tasks with `changed` within 14 days of the page stamp (a task with no readable `changed` stays). It keeps `spec`, `updated` and the other top-level keys, adds `omitted` and `full_registry`, and writes the JSON minified. `full_registry` is `docs/<record folder>/registry.json`, from `record_dir` when its last two parts are `docs/project` or `docs/artifacts`, else `docs/project/registry.json`. ARTIFACTSPEC R5.9 updated.
- **D26 + D29 no old Live rows.** `details.earlier` is gone. Live rows older than 14 days are not drawn. `group built` holds `<p class="earlier-note">N earlier Live tasks (over 14 days old) are not shown; the full list is in <path>`. The fold count reads `1 built, 8 live, 270 earlier` (or `N shown, M earlier` with no Built row). R6.3 and the R6.12 sentence updated. Feature artifacts never had the fold; they still have none and no line. Old Dropped rows are still drawn (the decisions name Live only).
- **D27 no `data-label`.** Removed from checklist rows, the feature-list rows and the feature State cell. `table.status-checklist` gets class `with-app` on Full Progress (it has the App / service column); the narrow-box CSS sets `content` per `td:nth-child(n)::before`, with the same texts as the old attributes (App / service, Detail, Expected; Last updated, Tasks, State, Where it stands). The CI-runs table keeps its own `data-label`.

## Checker rules changed (render_artifacts.py `check_html`)

- R5.9: the embedded JSON must equal the registry window (plus a `full_registry` string ending `registry.json`). A feature artifact still embeds none.
- R6.3: no `details.earlier`; exactly one `earlier-note` in group `built`, with the exact text and count; none when no Live row is old; none in a feature artifact; no row drawn for an old Live task.
- INV-1 and R6.5: a task counted in the earlier line is not "missing from the checklist".
- The old folded-row checks (`folded_wanted`, row order of folded rows, release line of folded rows) are removed.

## Sizes

- This repository's own record (`docs/project`), full-progress page, rendered by the old and the new renderer without CI-runs: old 640,653 bytes, new 397,204 bytes.
- Test registry of 281 tasks (270 old Live): old-shape estimate 132,538 bytes, new 52,542 bytes (printed by the new test).

## Tests

- `python3 -I tools/test_render_artifacts.py`: 163 passed, 0 failed. Updated the cases that asserted the full registry, the Earlier fold, or `data-label`.
- `python3 -m unittest discover -s claude/plugins/docs/tests`: 194 OK, including new `test_ar69_lighter_full_progress.py` (5 tests).
- `tools/test_artifacts_ar59`, `ar63`, `ar66`, `test_ci_areas`: all pass.
- `tools/test_project_artifacts.py`: two cases needed updates (`data-label` regex, table class selector, one `render` after `move-record`); both pass by name; the remaining 137 passed in the full run. The CI job `artifact renderer, commands and hooks` runs it whole and passed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only G1 (stale generated `decisions.md` on `main`, not committed here) and W1 (this report under `docs/work/`, stripped before the join). Both are expected.
- CI, `gh workflow run spec-lint.yml --ref AR69-lighter-full-progress -f areas=docs,artifacts`:
  - run 42993720590 (first head): `docs check` failed (G1, W1); `artifact renderer, commands and hooks` failed (two tests, fixed after); `docs plugin` success.
  - run 42994082435 (head with the fixes): `which areas does this change touch` success; `docs plugin` success; `artifact renderer, commands and hooks` success; `docs check` failure with only G1 and W1.

## Notes and follow-ups

- Tests for the renderer live in `tools/`, not `claude/plugins/docs/tests/`; I edited them there. The new test is in the plugin tests dir and imports the `tools` fixture.
- I did not touch the `Changes in` line of ARTIFACTSPEC (a change log; the release fold writes it). The feature spec `docs/features/artifacts/spec.md` does not restate R5.9/R6.3; its decision row D15 ("Which rows fold into Earlier?") is now out of date. Feature notes added for `features/artifacts` and `features/docs`.
- Not owned, left alone: `project_artifacts.py` comment (line ~772) still says the page embeds the whole registry; `README.md` of the docs plugin may mention the Earlier fold.
- `move-record` is a byte-for-byte move, so the page keeps naming the old registry path until the next `render`. `check` reports that (INV-3) as for any stale page.
- Old Dropped rows older than 14 days are drawn but not in the embedded window. Say if Dropped should fold too.
- The docs-plugin `tests/` rule on `docs/project/` was kept: nothing under `docs/project/` or generated files committed.

Branch head SHA: the commit that adds this report (code head before it: dc06411).

READY
