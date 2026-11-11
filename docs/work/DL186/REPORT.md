# DL186 report

## Base check
`claude/plugins/delivery/.claude-plugin/plugin.json` version is 1.25.0 (ok). Branch made from origin/main.

## Single source
`claude/plugins/delivery/templates/shared/.gitleaks.toml`, moved with `git mv` from the tech-stack-setup assets. Why delivery: its installer already writes every CI file, and tech-stack-setup already calls it at the end of step 1. Two copies in two plugins would drift, and a plugin cannot rely on another plugin's folder at install time. tech-stack-setup now carries no copy and its Phase 7 table lists `.gitleaks.toml` under the delivery installer.

## What changed
- `delivery_ci_install.py`: `.gitleaks.toml` is project-owned. `install` writes it when missing and keeps a different one. `update` never overwrites it.
- Rules `project-named-secret` and `project-database-url`: one line only (`[ \t]`, no `\s`), `=` needs a non-empty value that is not a comment, `:` needs a quoted value (database URL also allows a `scheme://` value). Types, fields and empty keys no longer match.
- Root `/.gitleaks.toml` carried the same two rules; same fix applied. A test checks the root and shared rules are identical.
- tech-stack-setup SKILL.md Phase 7 lines and `assets/tooling/README.md`; delivery spec R13.3 and project-setup spec R5.2 text; feature notes and change notes for both plugin.json files.

## Tests
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests -p "test_dl186*"`: 9 tests OK. Includes the real gitleaks binary (`gitleaks dir` on a temp folder): the 10 false-positive lines give exit 0, the real secrets give exit 1.
- Full delivery tests dir: OK (skipped=1).
- `change_notes.py check --config tools/change-notes.json`: ok.
- `docs_check.py`: only W1 (this report), as expected.
- Not run locally (session guard: heavy suites): `test_project_setup_fixes.py`, `test_ci_areas.py`. CI covers them.
- ci_areas.py: `claude/plugins/delivery/.*` already maps to the delivery area, which runs the tests dir; no change needed. `.claude/suites.json` lists only `tools/test_*.py` suites, so no entry.
- CI: `spec-lint.yml --ref DL186-gitleaks-config -f areas=delivery,docs,profiles`, run 42933798286. Every job ended. All passed or were skipped (areas not selected) except `docs check`, which failed only on W1 (this report under docs/work, stripped before the join).

## Follow-ups
- `let api_key = String::new();` style lines still match the `=` branch; not in scope.
- Unquoted YAML `my_token: abc` no longer matches the custom rule (gitleaks defaults may still catch it).
- Projects that already copied the old rules keep them (project-owned); they must copy the new file by hand.

Branch head SHA: see `git rev-parse DL186-gitleaks-config` (code commit edb224f; the report commit follows it).

READY
