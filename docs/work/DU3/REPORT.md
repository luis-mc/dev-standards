# DU3 report

## What changed
- C1 Tabs: line added (panels stay mounted, a tab keeps its state).
- C2 Pager: line added (the pager takes a noun, "Files 1-24 of 32").
- C3 Filter bar: added to the list toolbar (component 11): search, Filter with active count, labelled always-visible Sort, chips with Clear all, filters in a sheet ending "Show N items", not sticky.
- C4 Change review: new section 34 before "How to add a component".
- C5 Looks line on all 34 components; "How to add a component" asks for five lines and no values.
- R17: emoji line added to "33. Other shared parts".
- T1: "Text on a fill" pairs (solid on-X, tint and on-tint) in tokens.md. Existing `-bg` tokens kept (gallery_draw.py reads them); they are noted as equal to the tint.
- T2: `--ds-duration-reduced`, `-screen`, `-progress`, `-toast`.
- T3: `--ds-page-gutter`, `--ds-page-padding` per breakpoint; frame widths; control heights.
- T4: closed border-width list (thin, medium, thick, double) with uses.
- T5: weight tokens and a Ceiling column per type role.
- 7:1: one sentence under "How themes work".
- Notes: docs/architecture/changes/DU3-docs.md, docs/features/docs/changes/DU3.md.

## CHANGES lines
- Components: added Looks line to every component; filter bar (11); tabs and pager lines; change review (34); emoji rule (33). How to add asks for five lines.
- Tokens: text-on-fill pairs; motion tokens reduced, screen, progress, toast; per-width gutter and padding; frame widths; control heights; closed border widths; weight tokens and per-role ceiling; 7:1 option for dark body text.

## Tests
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff, treat as every area" (heavy; not run, no Docker).
- `python3 -m unittest test_design_system test_ds184` (docs/tests): 50 tests, 1 FAIL: test_every_starter_component_has_a_drawing, 33 != 34. Cause: new component 34 has no drawing in `claude/plugins/docs/scripts/gallery_draw.py`, which I do not own. Passes (50 OK) on main. Needs a follow-up that adds a drawing for 34 (or merge DU3 with it).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 1 warning (T2 test-cost spec, not mine).

Branch head SHA: see the final commit on DU3-starter-components.

NOT READY
