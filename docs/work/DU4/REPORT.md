# DU4 report

## Fixes
- F1: every script in owns drops a lone `--` in `main(argv)` (done in each main; I do not own docs_lib.py).
- F2: DS4 for next-version is information only on a branch that is not the default branch (default from docs/docs.json, else main; no git or detached HEAD counts as default, so it still warns). It shows in `status` as INFO. The join (`join.py`, `rebuild_draft_gallery`) runs `design_system.py visuals next-version` after the merges and strip when a merged branch changed `docs/design-system/next-version/`, commits it, and skips with a message when the plugin is missing. The luismc-docs script is found like docs_work.py (`find_docs_script`).
- F3: `design_system.py relink vN [--base REF] [--apply]` (base default HEAD). Link-only means: same line count, each changed line differs only in markdown `](target)`, `<a href>`, or backticked repo paths, and each new target exists. It records the new digest and a `relinked` entry (date, files). The branch diff DS2 also accepts a link-only M. The freeze guard template (`design-system-freeze.test.ts`, `isLinkOnlyChange` in `design-system.ts`) does the same. DOCSPEC R15.5 text updated; R15.7a got one clause about DS4.
- F4: promote and the next-version template CHANGES.md end with `<!-- - C1: what changed (file; source) -->`.
- F5: next-version README template has "What the apps do not follow yet"; the design-system README template says to keep it current until the implementation is approved. I also added one sentence about `relink` there.

## Decisions to check
- A relinked numbered version keeps a stale gallery (the README is part of the gallery's source digest and a frozen version cannot be rebuilt). So DS4 "source" is skipped for a numbered version that has a `relinked` record.
- `design_system.py visuals` takes the version as a positional argument (the docstring says `--version`); join uses the positional form.
- Not in owns, left alone: the join has no case in tools/test_delivery_gate.py for the rebuild; the new test is in the docs tests (test_du4.py, JoinGalleryTests).
- docs_check: G1 (generated decisions.md stale) is not mine and I did not commit generated files. W1 is the expected docs/work/ warning.

## New tests (claude/plugins/docs/tests/test_du4.py)
LoneDashDashTests (2), Ds4BranchTests (4), RelinkTests (5), ChangesAndReadmeTests (3), JoinGalleryTests (1). I changed one old assertion in test_design_system.py (`- C1` is now matched as a line start, because the comment holds the text).

## Commands
- `python3 -I -m unittest discover -s claude/plugins/docs/tests -t claude/plugins/docs/tests`: Ran 165, OK.
- `python3 -I tools/test_ds_guard_templates.py`: OK (3 cases pass, node 22).
- `python3 tools/ci_areas.py --branch-advice`: heavy: delivery -> `gh workflow run spec-lint.yml ... areas=specs,delivery,docs`. Not run (heavy, needs gh).
- `python3 tools/test_delivery_gate.py --no-mutants -k join_docs_strip`: 12 checks, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only G1 (generated, stale before this task) and W1 (this report) remain.

Branch head: see the last push (git rev-parse DU4-docs-plugin-fixes).
READY
