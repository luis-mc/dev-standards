"""DL100: a cloud create must clear the account's connectors (DL-93)."""
import unittest
from unittest import mock

from _helpers import make_root
import hook_pre_tool as P
import hooklib as H

BRIEF = "```delivery\ntask: X1\n```\nDo it (no UI change)"


def create(extra, action="create", cfg=None):
    root = make_root()
    body = {"session_context": {"effort_level": "medium", "model": "sonnet"},
            "events": [{"data": {"message": {"content": BRIEF}}}]}
    body.update(extra)
    data = {"tool_name": "RemoteTrigger", "tool_input": {"action": action, "body": body}, "cwd": str(root)}
    try:
        P.check_launch(cfg or H.load_config(str(root)), H.load_ledger(str(root)), data, "cloud")
    except P.Deny as d:
        return str(d)
    return None


class ConnectorTests(unittest.TestCase):
    def test_missing_clear_is_refused(self):
        out = create({})
        self.assertIn("DL-93", out)
        self.assertIn("clear_mcp_connections", out)

    def test_clear_true_passes(self):
        self.assertIsNone(create({"mcp_connections": [], "clear_mcp_connections": True}))

    def test_clear_false_is_refused(self):
        self.assertIn("DL-93", create({"mcp_connections": [], "clear_mcp_connections": False}))

    def test_listed_connectors_pass(self):
        self.assertIsNone(create({"mcp_connections": [{"name": "example-docs"}]}))

    def test_run_action_is_not_checked(self):
        self.assertIsNone(create({}, action="run"))

    def test_can_be_switched_off(self):
        root = make_root()
        cfg = H.load_config(str(root))
        cfg["checks_off"] = ["DL-93"]
        self.assertIsNone(create({}, cfg=cfg))


if __name__ == "__main__":
    unittest.main()
