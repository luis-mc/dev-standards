# DU6 report

## What was drawn
- Component 34 "Change review": summary bar of counts (buttons that filter), change chips with counts, rows with tick and a word mark (+ New, ~ Changed, ! Conflict) plus a line style (conflict dashed), conflict unticked with a reason line, one sticky "Apply 12 changes" bar.
- Component 11 list toolbar: search, "Filter (2)" button, labelled Sort, count, active chips with Clear all, and a filter sheet ending "Show 12 items".
- gallery_draw.token_kind_samples: text-on-fill and on-tint pairs as text-on-swatch with ratio; border widths; weight per role with ceiling check; motion, per-width, frame and control-height tables.
- gallery_tokens: role table read by header (new Ceiling column no longer shifts Family); per-width tables read; fill_pairs and with_prefix helpers. Old -bg tokens still read.
- Test added: test_gallery_shows_fill_pair_border_widths_and_change_review.

## Files outside my ownership (needed, please check)
- claude/plugins/docs/scripts/design_system.py: one call to G.token_kind_samples in _token_samples, and GALLERY_SCRIPT_VERSION 1 -> 2. Without the call the new sections cannot reach the page.
- components.md and tokens.md: no change needed.

## Tests
- `cd claude/plugins/docs/tests && python3 -m unittest test_design_system test_ds184`: 51 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff, treat as every area" (a workflow run; not run here).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error W1 (docs/work, expected), 1 warning T2 (test-cost spec, not mine).
- E2E: gallery built once from the starter; the HTML has component 34 (id component-34) and no network references. Build output deleted, not committed.

Branch head SHA: see the final commit on DU6-gallery.

READY
