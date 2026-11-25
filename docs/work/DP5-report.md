# DP5 report: spec-lint paths

Finding: spec-lint was already scoped by area (DS43). All area jobs (specs, delivery x12, profiles, artifacts, transcript-folds, docs) wait on `areas`. The one ungated doc job was `docs-check`: it ran on every run, including draft PRs, DS44 skips and `.claude/`-only changes.

Change: new `docs_check` output in `tools/ci_areas.py` (`docs_check_flag`, added in `main()`; `classify()` unchanged so its tests hold). `docs-check` now has `needs: areas` and `if: docs_check == 'true'`. No new `paths` filter.

docs_check is true for: any path under docs/, claude/, tools/, .github/workflows/, or AGENTS.md/CLAUDE.md; every push to main that is not a DS44 skip; every unreadable range; a dispatch naming docs or specs.

| Change type | Jobs before | Jobs after |
|---|---|---|
| docs/ only | areas, change-notes, docs-check | same |
| spec reference | areas, specs, change-notes, docs-check | same |
| plugin code (delivery) | areas, delivery jobs + gate, change-notes, docs-check | same |
| tools/ unmapped | all areas, change-notes, docs-check | same |
| .claude/settings.json | areas, specs, change-notes, docs-check | areas, specs, change-notes |
| other .claude/** | areas, change-notes, docs-check | areas, change-notes |
| draft PR | docs-check | none |
| ready release PR | full suite | full suite |
| push to main | full suite | full suite |
| push to main, DS44 skip | docs-check | none (content already tested) |

Docs and spec changes still run every doc job; no plugin guard is skipped. Verified: docs_check_flag cases, YAML parse, branch advice "light". Not run: tools/test_ci_areas.py (session guard says heavy, CI runs it). No test added for docs_check_flag: that file is outside this task's ownership.

Notes: docs/guides/changes/testing/DP5.md, docs/features/test-cost change note. Guide text added to docs/guides/testing.md.
