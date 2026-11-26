# DS274 to DS277 report

Built: release-scoped fold (docs_fold.py and change_notes.py, `--all`), Stop hook names every release of a pull request, DL-124 treats a merged, not yet cleaned or smoked entry as active, and `delivery_ledger.py link` sets the PR on the releases of its cargo.

Tests run: the four new delivery tests, the new docs test, test_fold, test_ds252, test_dl243, test_stop, test_ledger, test_ds267.

Not verified: `link` against a real record script (the test uses a stub runner); change_notes.py fold end to end on a real spec.
