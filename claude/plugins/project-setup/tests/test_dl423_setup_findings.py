#!/usr/bin/env python3
"""DL423 / DL427: branch-name suggestion in the update offer and skill; the tzdata step and its status line."""
import sys
import unittest
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import plugin_update_offer as U  # noqa: E402
from test_so9_update_offer import make_world  # noqa: E402

SKILL = (HERE.parent / "skills/claude-setup/SKILL.md").read_text("utf-8")


class SetupFindings(unittest.TestCase):
    def test_offer_suggests_integration_branch(self):
        with tempfile.TemporaryDirectory() as t:
            proj, cfg = make_world(Path(t), {"luismc-docs": "2.19.0"})
            assert "<task>-integration" in U.offer(proj, cfg)

    def test_skill_suggests_integration_branch_when_telling_owner_to_commit(self):
        line = next(l for l in SKILL.splitlines() if l.startswith("1. Commit and push"))
        assert "<task>-integration" in line

    def test_skill_tzdata_is_a_confirmed_checked_step_with_status_line(self):
        assert "python -m pip install --user tzdata" in SKILL
        assert "checked step" in SKILL
        assert any(l.startswith("- **time zone data**") and "tzdata: missing" in l for l in SKILL.splitlines())


if __name__ == "__main__":
    unittest.main()
