import unittest
from unittest import mock

from _helpers import make_root
import hook_pre_tool as P
import hooklib as H

GATE = "pnpm check:branch --keep-going --time-limit 75"
JOIN_BRIEF = "```delivery\ntask: RELEASE-101\nbranch: release/101\n```\nJoin the agent branches, then run " + GATE


def run(root, tool, tool_input, branch=None, cfg=None):
    """Deny reason or None for one call; `branch` is what git reports in the tool's cwd."""
    data = {"tool_name": tool, "tool_input": tool_input, "cwd": str(root)}
    cfg = cfg if cfg is not None else H.load_config(str(root))
    try:
        with mock.patch.object(P, "current_branch", return_value=branch):
            if tool in ("Bash", "PowerShell"):
                P.check_bash(str(root), cfg, H.load_ledger(str(root)), data, H.now())
            else:
                P.check_launch(cfg, H.load_ledger(str(root)), data, "cloud" if tool == "RemoteTrigger" else "local")
    except P.Deny as d:
        return str(d)
    return None


def bash(root, cmd, branch, cfg=None):
    return run(root, "Bash", {"command": cmd}, branch, cfg)


class JoinGateCommandTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()

    def test_gate_on_release_branch_denied(self):
        r = bash(self.root, GATE, "release/101")
        self.assertIn("DL-11", r)
        self.assertIn("release/101", r)

    def test_other_gate_forms_denied(self):
        for cmd in ("python tools/branch_gate.py", "python tools/run_suite.py --full", "npm run check:branch"):
            self.assertIn("DL-11", bash(self.root, cmd, "release/101b"), cmd)

    def test_gate_on_agent_branch_allowed(self):
        self.assertIsNone(bash(self.root, GATE, "claude/DV1-x"))

    def test_gate_on_master_allowed(self):
        self.assertIsNone(bash(self.root, "pnpm check:branch", "master"))

    def test_light_steps_on_release_allowed(self):
        for cmd in ("pnpm typecheck", "pnpm lint", "python fast_guards.py", "python tools/run_suite.py"):
            self.assertIsNone(bash(self.root, cmd, "release/101"), cmd)

    def test_checkout_earlier_in_command_decides(self):
        self.assertIn("DL-11", bash(self.root, "git checkout release/101 && " + GATE, "master"))
        self.assertIsNone(bash(self.root, "git checkout claude/DV1-x && " + GATE, "release/101"))

    def test_head_flag_decides(self):
        self.assertIn("DL-11", bash(self.root, "python branch_gate.py --head release/7", "master"))

    def test_custom_pattern_and_integration(self):
        cfg = H.load_config(str(self.root))
        cfg["join_branch_re"] = r"^rel-\d+$"
        self.assertIn("DL-11", bash(self.root, GATE, "rel-3", cfg))
        self.assertIn("DL-11", bash(self.root, GATE, "v2-integration", cfg))

    def test_wide_train_patterns_leave_agent_branches_alone(self):
        # a project may set both to ^(release|claude)/ for the watcher; an agent's own gate stays allowed
        cfg = H.load_config(str(self.root))
        cfg["train_branch_re"] = cfg["release_branch_re"] = r"^(release|claude)/"
        self.assertIsNone(bash(self.root, GATE, "claude/DV1-x", cfg))
        self.assertIn("DL-11", bash(self.root, GATE, "release/101", cfg))
        r = run(self.root, "Agent", {"prompt": "```delivery\nbranch: claude/DV9-x\n```\nFix bug, run " + GATE}, cfg=cfg)
        self.assertFalse(r and "DL-11" in r)

    def test_switched_off_allows(self):
        cfg = H.load_config(str(self.root))
        cfg["checks_off"] = ["DL-11"]
        self.assertIsNone(bash(self.root, GATE, "release/101", cfg))

    def test_mutant_release_test_dropped(self):
        # without the release-branch test the agent-branch case would be denied; with it always false, release passes
        with mock.patch.object(H, "is_release_branch", return_value=True):
            self.assertIn("DL-11", bash(self.root, GATE, "claude/DV1-x"))
        with mock.patch.object(H, "is_release_branch", return_value=False):
            self.assertIsNone(bash(self.root, GATE, "release/101"))


class JoinBriefTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()

    def cloud(self, text):
        return {"action": "run", "body": {"events": [{"data": {"message": {"content": text}}}]}}

    def test_local_join_brief_denied(self):
        self.assertIn("DL-11", run(self.root, "Agent", {"prompt": JOIN_BRIEF}))

    def test_cloud_join_brief_denied(self):
        self.assertIn("DL-11", run(self.root, "RemoteTrigger", self.cloud(JOIN_BRIEF)))

    def test_join_detected_by_text(self):
        for text in ("Run join.py then pnpm check:branch", "Join RELEASE-101 and use --full"):
            self.assertIn("DL-11", run(self.root, "Agent", {"prompt": text}), text)

    def test_light_join_brief_not_denied_by_dl11(self):
        r = run(self.root, "Agent", {"prompt": "```delivery\nbranch: release/101\n```\nJoin: merge, typecheck, lint"})
        self.assertFalse(r and "DL-11" in r)

    def test_non_join_brief_with_gate_allowed_by_dl11(self):
        r = run(self.root, "Agent", {"prompt": "```delivery\nbranch: claude/DV9-x\n```\nFix bug, run " + GATE})
        self.assertFalse(r and "DL-11" in r)

    def test_switched_off_allows(self):
        cfg = H.load_config(str(self.root))
        cfg["checks_off"] = ["DL-11"]
        r = run(self.root, "Agent", {"prompt": JOIN_BRIEF}, cfg=cfg)
        self.assertFalse(r and "DL-11" in r)


class RemoteTriggerActionTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()

    def launch(self, action, model=True, cfg=None):
        body = {"session_context": {"effort_level": "medium"}, "events": [{"data": {"message": {"content": "```delivery\ntask: X1\n```\nDo it"}}}]}
        if model:
            body["session_context"]["model"] = "sonnet"
        return run(self.root, "RemoteTrigger", {"action": action, "body": body}, cfg=cfg)

    def test_update_disable_passes(self):
        self.assertIsNone(run(self.root, "RemoteTrigger", {"action": "update", "trigger_id": "t1", "body": {"enabled": False}}))

    def test_read_actions_pass(self):
        for a in ("list", "get", "list_runs", "get_run_log"):
            self.assertIsNone(run(self.root, "RemoteTrigger", {"action": a, "trigger_id": "t1"}), a)

    def test_create_and_run_without_model_refused(self):
        for a in ("create", "run"):
            self.assertIn("DL-37", self.launch(a, model=False) or "", a)

    def test_cap_counts_create_and_run(self):
        cfg = H.load_config(str(self.root))
        cfg["caps"] = {"cloud": 0, "local": 0, "total": 0}
        cfg["brief_markers"] = []
        for a in ("create", "run"):
            self.assertIn("DL-38", self.launch(a, cfg=cfg) or "", a)
        self.assertIsNone(run(self.root, "RemoteTrigger", {"action": "update", "body": {"enabled": False}}, cfg=cfg))


if __name__ == "__main__":
    unittest.main()
