# DS184 report: docs plugin fixes (F1 to F13)

Method: a failing test first (`claude/plugins/docs/tests/test_ds184.py`), then the fix. All findings reproduced on current main.

| Finding | Result | Evidence |
|---|---|---|
| F1 new folder escapes M1 | fixed | `git status -uall` in `changed_files`; test_f1 |
| F2 any note clears M1 | fixed | only the doc's own notes folder counts; test_f2 |
| F3 master repo, silent | fixed | init detects the branch; check warns when no base; test_f3 (x2) |
| F4 BOM | fixed | `D.read` strips U+FEFF; test_f4 |
| F5 git output locale | fixed | `encoding="utf-8", errors="replace"` in `D.git` and `check_reference`; test_f5 |
| F6 W1 fails report branches | by design | R8.1/R10.2 and the brief: W1 is meant to fail a branch headed to the default branch until the join strips `docs/work/`. `docs_check` on this branch reports no W1 problem beyond that intent. No code or DOCSPEC change. |
| F7 underscore anchors | fixed | `heading_slug` keeps `_`; test_f7 |
| F8 percent-encoded links | fixed | `unquote` in `check_links` and the site link fix; test_f8 |
| F9 unquoted title | fixed | `format_value` quotes ' #', ': ', leading `[`/quote; test_f9 |
| F10 inline code rewritten | fixed | inline code protected in `rewrite_links`; test_f10 |
| F11 aligned separator | fixed | regex accepts `:---`; test_f11 |
| F12 octal paths | fixed | `-c core.quotePath=false`; test_f12 |
| F13 impossible date | fixed | `date.fromisoformat` check in promote and approve-implementation; test_f13 |

Hooks: `hooks.json` now uses `if command -v python3 ...; then python3 X; else python X; fi` (test_hooks_keep_exit_code).

Other edits: `test_hooks.py` spy skips the new `-c` args; `docs_index.py` site link fix (F8).

Tests run: `python3 -m unittest discover -s tests` in `claude/plugins/docs`: 146 tests OK. `docs_check.py --no-reference` on this repo: see last run below.

Branch head SHA: see the pushed branch head.

READY
