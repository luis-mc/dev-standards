# DL257 report: Windows join tests

Failing: test_dl241_join_siblings.test_skipped_lines_with_push; test_delivery_gate -k join: 5 checks (join_clean no-ff merge, join_clean quick check head, join_same_tree tree, join_conflicts Join commit, join_conflicts two parents).

Causes: (1) sibling files A.txt/B.txt/C.txt collide with a.txt on a case-insensitive Windows disk. (2) join.py finds the docs plugin in the machine plugin cache when LUISMC_DOCS_WORK is unset, adding a Rebuild generated docs commit; CI has no plugin.

Changes (test-only): test_dl241_join_siblings.py uses sib-A.txt etc, writes LF, sets core.autocrlf false; tools/test_delivery_gate.py env_with defaults LUISMC_DOCS_WORK to a missing path.

Docs: none, test-only Windows fixes.

Tests on Windows: gate -k join 99 checks 5 failed -> 0 failed. unittest join discover 45 tests 1 failure -> OK (1 skipped, pre-existing).

READY
