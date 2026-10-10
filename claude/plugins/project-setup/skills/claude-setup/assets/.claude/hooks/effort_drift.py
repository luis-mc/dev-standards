#!/usr/bin/env python3
"""SessionStart hook: warn when the session's model has no saved effort level.

claude-setup saves the chosen effort per model as
`modelSettings.<model ID>.effortLevel`. When the `opus` or `sonnet` alias later
moves to a new model ID, the new model has no entry and silently falls back to
its default effort. This hook notices that at session start.

Input: the SessionStart JSON on stdin. Its `model` field is the active model
identifier, but Claude Code may omit it (for example after `/clear`). When it
is absent the hook checks the IDs in ANTHROPIC_DEFAULT_OPUS_MODEL and
ANTHROPIC_DEFAULT_SONNET_MODEL instead, when those are set; with neither it
has nothing to check and stays silent.

Output: a `systemMessage` JSON object, which Claude Code shows to the user.
Plain stdout would go to Claude's context instead. Always exits 0.

Disable: set CLAUDE_SETUP_EFFORT_DRIFT=off in the settings `env` block or the
shell, or delete the SessionStart entry that runs this file.

Standard library only.
"""
import json
import os
import re
import sys
from pathlib import Path

DISABLE_VALUES = {"0", "off", "false", "no"}
ENV_IDS = ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL")
FAMILIES = ("opus", "sonnet")  # the models claude-setup saves an effort for


def base_id(model):
    """Drop a context-window suffix such as `[1m]`."""
    return re.sub(r"\[[^\]]*\]$", "", model.strip())


def settings_files(home, project_dir):
    files = [Path(home) / ".claude" / "settings.json"]
    if project_dir:
        files.append(Path(project_dir) / ".claude" / "settings.json")
        files.append(Path(project_dir) / ".claude" / "settings.local.json")
    return files


def saved_entries(home, project_dir):
    """Model IDs that have a modelSettings.<ID>.effortLevel in any file."""
    ids = set()
    for path in settings_files(home, project_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("modelSettings")
            if not isinstance(entries, dict):
                continue
            for key, value in entries.items():
                if isinstance(value, dict) and value.get("effortLevel"):
                    ids.add(key)
        except (OSError, ValueError, AttributeError):
            continue  # missing or unreadable file: nothing saved there
    return ids


def candidate_ids(data, env):
    model = data.get("model")
    if isinstance(model, str) and model.strip():
        return [model], "session model"
    found = [env[k] for k in ENV_IDS if env.get(k, "").strip()]
    return found, "default model alias"


def evaluate(data, env, home):
    """Return the warning text, or None when nothing is wrong."""
    if env.get("CLAUDE_SETUP_EFFORT_DRIFT", "").strip().lower() in DISABLE_VALUES:
        return None
    ids, source = candidate_ids(data, env)
    ids = [i for i in ids if any(f in i.lower() for f in FAMILIES)]
    if not ids:
        return None
    project_dir = env.get("CLAUDE_PROJECT_DIR") or data.get("cwd")
    saved = saved_entries(home, project_dir)
    missing = [i for i in ids if i not in saved and base_id(i) not in saved]
    if not missing:
        return None
    return (
        "No saved effort level for " + ", ".join(sorted(set(missing)))
        + f" ({source}); it runs at its default effort. Re-run "
        "/luismc-project-setup:claude-setup to pick one."
    )


def main():
    try:
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        message = evaluate(data, os.environ, str(Path.home()))
        if message:
            print(json.dumps({"systemMessage": message}))
    except Exception:  # a warning hook must never get in the way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
