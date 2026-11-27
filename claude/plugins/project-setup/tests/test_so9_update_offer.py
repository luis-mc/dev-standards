#!/usr/bin/env python3
"""SO9: the plugin update offer (scripts/plugin_update_offer.py)."""
import json
import os
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "plugin_update_offer.py"
sys.path.insert(0, str(SCRIPT.parent))
import plugin_update_offer as U  # noqa: E402


def make_world(tmp: Path, versions: dict, enabled=True, stamp=None):
    """A config dir with one marketplace checkout and a project."""
    mk = tmp / "mk"
    for name, ver in versions.items():
        d = mk / "claude/plugins" / name.replace("luismc-", "") / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(json.dumps({"name": name, "version": ver}), "utf-8")
    cfg = tmp / "cfg"
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins/known_marketplaces.json").write_text(json.dumps({"m": {"installLocation": str(mk)}}), "utf-8")
    proj = tmp / "proj"
    (proj / ".claude").mkdir(parents=True)
    if enabled:
        (proj / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"luismc-docs@m": True}}), "utf-8")
    if stamp is not None:
        (proj / ".claude/plugin-versions.json").write_text(json.dumps(stamp), "utf-8")
    return proj, cfg


class UpdateOffer(unittest.TestCase):
    def test_changes_lines(self):
        got = U.changes({"a": "2", "b": "1", "c": "5"}, {"a": "1", "b": "1"})
        assert got == ["a 1 -> 2", "c 5 (new here)"]

    def test_offer_when_version_changed(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"}, stamp={"applied": {"luismc-docs": "2.17.0"}})
            text = U.offer(proj, cfg)
            assert "luismc-docs 2.17.0 -> 2.19.0" in text and "AskUserQuestion" in text and "claude-setup" in text

    def test_no_offer_when_in_step_declined_or_not_a_project(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"}, stamp={"applied": {"luismc-docs": "2.19.0"}})
            assert U.offer(proj, cfg) == ""
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"}, stamp={"applied": {}, "declined": {"luismc-docs": "2.19.0"}})
            assert U.offer(proj, cfg) == ""
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"}, enabled=False)
            assert U.offer(proj, cfg) == ""

    def test_no_stamp_offers_everything_once(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"})
            assert "luismc-docs 2.19.0 (new here)" in U.offer(proj, cfg)

    def test_apply_and_decline_write_only_the_stamp(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"}, stamp={"applied": {"luismc-docs": "2.17.0"}})
            U.write_stamp(proj, "declined", cfg)
            assert U.offer(proj, cfg) == ""
            # a new plugin version asks again
            (Path(t) / "mk/claude/plugins/docs/.claude-plugin/plugin.json").write_text(json.dumps({"name": "luismc-docs", "version": "2.20.0"}), "utf-8")
            assert "2.17.0 -> 2.20.0" in U.offer(proj, cfg)
            U.write_stamp(proj, "applied", cfg)
            stamp = json.loads((proj / ".claude/plugin-versions.json").read_text("utf-8"))
            assert stamp == {"applied": {"luismc-docs": "2.20.0"}}
            assert U.offer(proj, cfg) == ""

    def test_hook_prints_json_and_fails_open(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"})
            env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proj), "CLAUDE_CONFIG_DIR": str(cfg)}
            r = subprocess.run([sys.executable, str(SCRIPT), "hook"], input="{}", capture_output=True, text=True, env=env)
            assert r.returncode == 0
            out = json.loads(r.stdout)["hookSpecificOutput"]
            assert out["hookEventName"] == "SessionStart" and "new here" in out["additionalContext"]
            env["CLAUDE_CONFIG_DIR"] = str(Path(t) / "nowhere")
            r = subprocess.run([sys.executable, str(SCRIPT), "hook"], input="{}", capture_output=True, text=True, env=env)
            assert r.returncode == 0 and r.stdout == ""

    def test_hooks_json_runs_the_script(self):
        h = json.loads((HERE.parent / "hooks/hooks.json").read_text("utf-8"))
        cmd = h["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert "plugin_update_offer.py" in cmd and "${CLAUDE_PLUGIN_ROOT}" in cmd


if __name__ == "__main__":
    unittest.main()
