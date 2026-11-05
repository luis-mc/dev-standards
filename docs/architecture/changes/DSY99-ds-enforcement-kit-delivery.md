---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
`references/design-gate.md` says how the design-system enforcement kit becomes a required check in the branch gate and in CI (all options). `scripts/hook_design_edit.py` is wired in hooks.json (PreToolUse on Edit, MultiEdit and Write; UserPromptSubmit and Stop reset its count): the first CSS or hand-made part edit in app code in a turn warns, a repeat in the same turn is denied (D231). `config-schema.json` gains `design_system.app_paths` and `shared_paths` (D232). The shared `change_notes.py check` fails a diff that adds an entry to, or raises a count in, a known list (`known_lists`, default `scripts/design/*.known.json`) that already exists at the base (D235).
