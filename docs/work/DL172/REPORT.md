# DL172 report: setup and delivery bounds (D183)

## Crossings found and decisions

| Crossing | Decision |
|---|---|
| `tech-stack-setup/assets/tooling/shared/.githooks/pre-push` (calls branch_gate, fast_guards, train_freeze) | Moved to `delivery/templates/shared/.githooks/pre-push`. Installer writes it at `.githooks/pre-push`. `install` moves a different foreign hook to `pre-push.local`. |
| `.githooks/commit-msg` (reads `.delivery/config.json` `no_attribution`) | Moved to `delivery/templates/shared/.githooks/commit-msg`. |
| `claude-setup/assets/delivery-config.json` | Moved to `delivery/templates/shared/.delivery/config.json`. Installer writes it without `_` keys, only when absent, also on `update` (never overwritten). `install --only config,settings` (no track) is what claude-setup calls. |
| `claude-setup/assets/.claude/settings.json` PreToolUse `session_guard.py` entry | Removed from the asset. `delivery_ci_install.py` merges it into `.claude/settings.json` (other entries kept, no duplicate, invalid JSON left alone with a warning). |
| `.githooks/pre-commit` (calls `change_notes.py` and `gate.json` only when present) | Stays in project-setup: it is a repo hook (secret scan, conflict markers); the delivery call is optional. |
| `.gitattributes`, `.gitleaks.toml`, linters, guard tests | Stay (repo tooling). |
| `claude-setup/assets/ci/dev-standards.yml` | Not moved. It is the docs/design check workflow, not the delivery CI, and `assets/ci` is outside my owns list. No CI workflow lives in tech-stack-setup. |
| claude-setup SKILL.md `.delivery/config.json` and "commit-msg installed by tech-stack-setup" text | Reworded to call the installer. |
| tech-stack-setup SKILL.md hook table and pre-push steps | Reworded: the installer writes the hooks. |
| docs only mentions (invariants.md, catalog, tooling/README.md, stack-profile.md, auth-setup) | Checked: they cite delivery rules or already say the installer writes the scripts. No change. |

## Files outside my owns list that had to change (they cited the moved paths)

`tools/ci_areas.py` (HOOKS path), `tools/test_ci_areas.py` (pre-push path), `tools/test_delivery_gate.py` (pre-push path, mutant copy), `claude/plugins/delivery/tests/test_dl130_gate_fixes.py`, `test_config.py`, `test_dl150_install_sync.py` (install now creates `.delivery/`). One-line path edits each.

## Tests

See the results appended below.
