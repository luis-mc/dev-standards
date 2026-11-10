# Hook list mismatch: ARTIFACTSPEC section 8 vs hooks.json

Status: decision for the owner. Nothing was changed in `hooks.json` or any script.

## What the spec says

`claude/plugins/artifacts/references/artifactspec.md`, section 8, first lines:
"All four hooks are registered in the plugin's `hooks/hooks.json`", and it lists
the after-command hook, the before-command hook for `Bash` and `PowerShell`,
the end-of-turn hook and the session-start hook. R8.16 also describes the
before-command hook (it pushes nothing and exits 0).

## What is registered

`claude/plugins/artifacts/hooks/hooks.json` registers:

- PostToolUse (`Bash|Agent|Task`) -> `hook_after_command.py`
- PostToolUseFailure (`Bash`) -> `hook_after_command.py`
- Stop -> `hook_end_of_turn.py`
- SessionStart -> `hook_session_start.py`

There is no PreToolUse entry. So three hook scripts are registered, not four.

## History

- `3a5ad29` (2026-10-10): plugin created; hooks.json added.
- `4f3e0bc` (2026-10-11): added a PreToolUse entry (`Bash|PowerShell` ->
  `hook_before_command.py`) to push the record before `gh pr create/ready/merge`.
  The spec gained the before-command hook in the same change.
- `ae0f273` (2026-10-12, AR50 "hooks never commit, push or fetch"): removed the
  PreToolUse entry from hooks.json. `hook_before_command.py` was reduced to a
  no-op (docstring: "no longer registered in hooks/hooks.json; the file stays so
  an older hooks.json entry cannot fail"). R8.16 was rewritten to "does not
  push". The tool test `hooks_json_registers_no_before_command_hook` in
  `tools/test_project_artifacts_hooks.py` now asserts the entry is absent.

## Which side is wrong

The spec. The removal was deliberate (AR50), the script and a test both say so.
The intro of section 8 was not updated when the registration went; R8.16 still
describes a hook that is not registered.

## Recommended fix (spec text, not hook registration)

Re-registering the hook would do nothing (it is a no-op) and would add a
process start on every Bash call. Instead, edit section 8:

1. Change "All four hooks" to "Three hooks" and drop the before-command bullet
   (or say it is retired: kept as a silent script, not registered).
2. Reword R8.16 to say the before-command hook is retired and not registered,
   keeping its test name. Keep the requirement ID.
3. Check the At a glance text (line ~183) for the old "new before-command hook"
   wording.

This is a spec change, so it needs a version bump and a change note under the
spec rules; that is for the owner to schedule.

Decision needed: fix the spec text (recommended), or restore the registration.
