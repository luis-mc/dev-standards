# DL120 report

## What changed
- `delivery_ci_install.py`: reads project file `scripts/delivery/ci-install.json`; its name is in PROJECT_OWNED_NAMES; docstring documents it.
- New template `templates/shared/scripts/delivery/ci-install.example.json` (empty `keep`/`skip`, `_comment`). Copied like any template; never read as the real file.
- Tests: `claude/plugins/delivery/tests/test_dl120_install_keep_skip.py`.
- Change note: `docs/architecture/changes/DL120-install-keep-skip.md`.

## Exact behaviour (for the spec)
- File: `scripts/delivery/ci-install.json`, keys `keep` and `skip`, lists of paths relative to the project root (`\` and a leading `./` are normalised). Never written or overwritten by install or update.
- keep: `update` never overwrites; when it would have, it lists `kept (ci-install.json) <path>` and at the end prints `kept <path>: the plugin's version differs; diff it with <template path> and fold your change into the plugin or drop it` (template path relative to the plugin, e.g. `templates/shared/scripts/delivery/ci_watch.py`). A kept file that is missing is still written.
- skip: install and update never write it, even when missing; listed as `skipped (ci-install.json) <path>`.
- A path in either list the plugin does not manage: `warning: scripts/delivery/ci-install.json lists <path>, which the plugin does not manage` (stdout, no effect on exit code).
- Bad JSON, non-object, or a key that is not a list of strings: one line on stderr naming `scripts/delivery/ci-install.json`, exit 2, nothing written.
- The import check (DL112) and the untracked check see skipped and kept files as they are on disk.
- No ci-install.json: same as before.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl120_install_keep_skip test_dl112_install_imports test_ci_options`: Ran 41, OK.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (branch not yet diffable locally); only the delivery tests above were run. No mutation, no Docker.
