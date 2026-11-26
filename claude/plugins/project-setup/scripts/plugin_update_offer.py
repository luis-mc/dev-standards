#!/usr/bin/env python3
"""SO9: when the luismc plugins are updated, offer to apply the new project config.

  python3 plugin_update_offer.py hook       SessionStart hook: prints the offer as additionalContext
  python3 plugin_update_offer.py status    what changed since the project was last set up (writes nothing)
  python3 plugin_update_offer.py apply     record the installed versions as applied (after claude-setup ran)
  python3 plugin_update_offer.py decline   record the installed versions as declined (do not ask again for them)

The stamp is `.claude/plugin-versions.json` in the project: {"applied": {plugin: version}, "declined": {...}}.
A project is one that turns on a luismc plugin in `.claude/settings.json`; any other directory gets no offer.
The script writes only that stamp. It never commits or pushes. Fails open. Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

STAMP = Path(".claude/plugin-versions.json")
SETTINGS = Path(".claude/settings.json")
PLUGIN_GLOB = "claude/plugins/*/.claude-plugin/plugin.json"


def project_root() -> Path:
    for key in ("CLAUDE_PROJECT_DIR",):
        if os.environ.get(key):
            return Path(os.environ[key])
    return Path.cwd()


def read_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def uses_luismc(root: Path) -> bool:
    plugins = read_json(root / SETTINGS).get("enabledPlugins")
    return isinstance(plugins, dict) and any(k.startswith("luismc-") and v for k, v in plugins.items())


def marketplace_root(config_dir: Path | None = None) -> Path | None:
    cfg = config_dir or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    known = read_json(cfg / "plugins/known_marketplaces.json")
    for entry in known.values():
        loc = entry.get("installLocation") if isinstance(entry, dict) else None
        if loc and any(Path(loc).glob(PLUGIN_GLOB)):
            return Path(loc)
    return None


def installed(config_dir: Path | None = None) -> dict[str, str]:
    """Plugin name -> version of the marketplace checkout the plugins are installed from."""
    root = marketplace_root(config_dir)
    out: dict[str, str] = {}
    for f in sorted(root.glob(PLUGIN_GLOB)) if root else []:
        d = read_json(f)
        if d.get("name") and d.get("version"):
            out[str(d["name"])] = str(d["version"])
    return out


def changes(now: dict[str, str], applied: dict[str, str]) -> list[str]:
    """One line per plugin that is new or whose version differs from the applied one."""
    lines = []
    for name, ver in now.items():
        old = applied.get(name)
        if old is None:
            lines.append(f"{name} {ver} (new here)")
        elif old != ver:
            lines.append(f"{name} {old} -> {ver}")
    return lines


def offer(root: Path, config_dir: Path | None = None) -> str:
    """The offer text, or '' when there is nothing to offer."""
    if not uses_luismc(root):
        return ""
    now = installed(config_dir)
    stamp = read_json(root / STAMP)
    if not now or stamp.get("declined") == now:
        return ""
    lines = changes(now, stamp.get("applied") or {})
    if not lines:
        return ""
    me = Path(__file__).resolve()
    return (
        "luismc plugins changed since this project was last set up:\n- " + "\n- ".join(lines) + "\n"
        "Ask the owner now, once, with AskUserQuestion: apply the new project config (CI workflow and its pin, "
        "settings, rules, docs)? Yes: run /luismc-project-setup:claude-setup (it adds what is missing and never "
        f"overwrites), then `python3 {me} apply`. No: run `python3 {me} decline`; it is not asked again until a plugin changes. "
        "When you tell the owner to commit the config change, suggest the branch name `<task>-integration`: the session guard "
        "refuses a ready pull request from any other branch name."
    )


def write_stamp(root: Path, key: str, config_dir: Path | None = None) -> dict[str, str]:
    now = installed(config_dir)
    stamp = read_json(root / STAMP)
    stamp[key] = now
    if key == "applied":
        stamp.pop("declined", None)
    p = root / STAMP
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n", "utf-8")
    return now


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "hook"
    try:
        root = project_root()
        if cmd == "hook":
            try:
                sys.stdin.read()
            except Exception:
                pass
            text = offer(root)
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        elif cmd == "status":
            print(offer(root) or "plugins in step with the project setup")
        elif cmd in ("apply", "decline"):
            now = write_stamp(root, "applied" if cmd == "apply" else "declined")
            print(f"{cmd}: recorded {len(now)} plugin versions in {STAMP}")
        else:
            print(__doc__)
            return 2
    except Exception as e:  # fail open: a hook must never break a session
        if cmd != "hook":
            print(f"plugin_update_offer: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
