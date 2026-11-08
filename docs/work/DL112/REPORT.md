# DL112 report

## What changed
- `ci_watch.py` and `fallback_launch.py`: the sibling import block is in a try/except. On `ModuleNotFoundError` it prints one line to stderr and exits 2:
  `<script>.py: <module>.py is missing from <folder>. Run `delivery_ci_install.py update --track <track>` from the plugin, then commit scripts/delivery/.`
- `delivery_ci_install.py`: after install/update (and with `--dry-run`) it reads the imports of every managed `scripts/delivery/*.py` with `ast` (top level and in functions). A shipped sibling module that is not on disk is listed under `missing imports:` as `  <script> imports <name>.py, which is not in <folder>`. In a git repo, managed files that exist but are not in `git ls-files` are listed under `not in git yet (commit them):`. No heading outside a git repo.
- Exit codes: 0 done, 1 bad track, 2 missing template folder, 3 a managed script imports a sibling that is not in the project (files are still written). Untracked files never change the exit code. A dry run only reports a missing module when the importing script is already in the project, so a dry run on an empty project exits 0 (it writes nothing, and the import check looks at disk).
- New test `test_dl112_install_imports.py` (closure of shipped imports for each track; missing import and exit 3; untracked list; no git; ci_watch subprocess error names ci_fallback.py).
- Change note `docs/architecture/changes/DL112-imported-modules-installed.md`.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl112_install_imports test_ci_options test_dl109_watcher_no_windows test_dl92_pool_fixes test_dl96_watcher_rearm test_post_tool` -> 141 OK
- `python3 -m unittest tools.test_delivery_fallback_launch tools.test_delivery_ci` -> 31 OK
- `python3 tools/ci_areas.py --branch-advice` -> "unreadable diff, treat as every area" (no origin diff in this sandbox); not run further.

## Notes
- `delivery_common.py` imports the plugin-only `delivery_ledger` optionally at run time; the closure test allows modules found in the plugin's `scripts/`.

Branch head SHA: cdfa93b (the report commit follows).
READY
