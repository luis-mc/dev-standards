# DL272 report

Base check: join.py on origin/main has `def stacked_on_older`. OK.

## What changed
- join.py: a stacked flag no longer refuses a branch up front. The merge runs; a clean merge prints one info line naming the older parent; a real conflict is refused with the new hint and the real conflicting files.
- stacked_on_older: a merge-base held by a third joined branch is shared work, so siblings are not stacked.
- conflict_files takes a reason, so a report never prints an empty list.
- Tests: new test_dl272_join_stacked_false_positive.py; DL128 and DL241 stacked tests now use a real conflict and the new hint.
- Docs: R5.40 sentence, feature note, change note.

## Tests
- tests/test_dl272, dl241, dl128, dl111, dl249, dl225, dl99: all OK.
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed.
- spec-lint.yml areas=delivery (run 43315638189): every delivery job passed; docs check failed only on W1 for docs/work/ (expected on a branch).
- Local docs_check also showed M1 for delivery-speed; answered with a `Docs: none` line in the commit message.

## Follow-ups
- Info line and conflict hint are printed only on the plain merge path, not after lockfile/generated-doc auto-resolves.

Branch head: see `git rev-parse origin/DL272-join-stacked-false-positive`.
READY
