"""Q-5 (no trickling), the rule text delivered at SessionStart, and the prompt recorder."""
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _helpers import L, SCRIPTS, make_root
import hook_post_tool as P

NOW = datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc)
PLUGIN = SCRIPTS.parent
ASSET = PLUGIN.parent / "project-setup/skills/claude-setup/assets/.claude/rules/clarifying-questions.md"
LONG = "Should RELEASE-29 merge now, given that the smoke test of RELEASE-28 passed an hour ago and CI is green?"


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


def agent(**kw):
    a = {"task": "DS1", "where": "cloud", "id": "a1", "state": "running", "launched_by": "s1", "started": ago(20)}
    a.update(kw)
    return a


def question(asked_at):
    return {"id": "Q1", "text": LONG, "asked_at": asked_at, "answered_at": ago(1), "blocks": []}


def run(script, root, data, cfg=None):
    data = dict({"cwd": str(root), "session_id": "s1"}, **data)
    env = dict(os.environ, DELIVERY_NOW=NOW.isoformat())
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / script)], input=json.dumps(data).encode(),
                       capture_output=True, env=env, timeout=60)
    out = p.stdout.decode().strip()
    return json.loads(out) if out else None


def ask(root, **kw):
    return run("hook_pre_tool.py", root, {"tool_name": "AskUserQuestion", "tool_input": {
        "questions": [{"question": LONG, "header": "Q", "options": [{"label": "a"}, {"label": "b"}]}]}, **kw})


def denied(res):
    return ((res or {}).get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def why(res):
    return ((res or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


def seed(root, agents=(), questions=(), prompt=None):
    def fn(led):
        led["agents"] = list(agents)
        led["owner_questions"] = list(questions)
        if prompt:
            led["owner_prompt"] = prompt
    L.update(root, fn)


class TrickleTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()

    def test_second_batch_while_agents_run_is_denied(self):
        seed(self.root, [agent()], [question(ago(20))], {"at": ago(40), "asked_for_questions": False})
        r = ask(self.root)
        self.assertTrue(denied(r))
        self.assertIn("Q-5", why(r))
        self.assertIn("ask everything at once", why(r))

    def test_first_batch_allowed(self):
        seed(self.root, [agent()], [], {"at": ago(40), "asked_for_questions": False})
        self.assertFalse(denied(ask(self.root)))

    def test_no_running_agent_allowed(self):
        seed(self.root, [agent(state="done")], [question(ago(20))])
        self.assertFalse(denied(ask(self.root)))

    def test_agent_of_another_session_ignored(self):
        seed(self.root, [agent(launched_by="other")], [question(ago(20))])
        self.assertFalse(denied(ask(self.root)))

    def test_dialogs_of_one_message_allowed(self):
        seed(self.root, [agent()], [question((NOW - timedelta(seconds=20)).isoformat())])
        self.assertFalse(denied(ask(self.root)))

    def test_batch_before_the_last_prompt_does_not_count(self):
        seed(self.root, [agent()], [question(ago(30))], {"at": ago(10), "asked_for_questions": False})
        self.assertFalse(denied(ask(self.root)))

    def test_batch_older_than_the_window_does_not_count(self):
        seed(self.root, [agent()], [question(ago(90))])
        self.assertFalse(denied(ask(self.root)))
        (self.root / ".delivery" / "config.json").write_text(json.dumps({"question_window_min": 120}))
        self.assertTrue(denied(ask(self.root)))

    def test_every_agent_blocked_on_owner_allowed(self):
        seed(self.root, [agent(blocked_on="owner"), agent(id="a2", blocked_on="owner")], [question(ago(20))])
        self.assertFalse(denied(ask(self.root)))
        seed(self.root, [agent(blocked_on="owner"), agent(id="a2")], [question(ago(20))])
        self.assertTrue(denied(ask(self.root)))

    def test_owner_asked_for_questions_allowed(self):
        seed(self.root, [agent()], [question(ago(20))], {"at": ago(25), "asked_for_questions": True})
        self.assertFalse(denied(ask(self.root)))

    def test_checks_off_disables(self):
        (self.root / ".delivery" / "config.json").write_text(json.dumps({"checks_off": ["Q-5"]}))
        seed(self.root, [agent()], [question(ago(20))])
        self.assertFalse(denied(ask(self.root)))


class RecorderTests(unittest.TestCase):
    def test_prompt_recorded_and_question_asked_for(self):
        root = make_root()
        for text, want in (("please ask me questions first", True), ("Ask me question about the DB", True),
                           ("merge the train", False)):
            P.handle({"hook_event_name": "UserPromptSubmit", "prompt": text, "session_id": "s1", "cwd": str(root)}, root)
            op = L.load(root)["owner_prompt"]
            self.assertEqual(op["asked_for_questions"], want, text)
            self.assertEqual(op["session"], "s1")

    def test_prompt_marks_open_questions_answered(self):
        root = make_root()
        P.handle({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "cwd": str(root),
                  "tool_input": {"questions": [{"question": LONG}]}}, root)
        self.assertIsNone(L.load(root)["owner_questions"][0]["answered_at"])
        P.handle({"hook_event_name": "UserPromptSubmit", "prompt": "yes", "cwd": str(root)}, root)
        self.assertIsNotNone(L.load(root)["owner_questions"][0]["answered_at"])

    def test_agent_row_records_launching_session(self):
        root = make_root()
        P.handle({"hook_event_name": "PostToolUse", "tool_name": "RemoteTrigger", "session_id": "s9", "cwd": str(root),
                  "tool_input": {"action": "run", "prompt": "```delivery\ntask: X\n```"},
                  "tool_response": {"trigger_id": "trig_1"}}, root)
        self.assertEqual(L.load(root)["agents"][0]["launched_by"], "s9")


class RulesDeliveryTests(unittest.TestCase):
    def test_session_start_injects_rules_without_tags(self):
        root = make_root()
        r = run("hook_session_start.py", root, {})
        ctx = r["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Interactive Constraints", ctx)
        self.assertIn("park a question until the agents of this wave report", ctx)
        self.assertNotIn("<!-- check", ctx)

    def test_no_delivery_folder_gets_nothing(self):
        import tempfile
        self.assertIsNone(run("hook_session_start.py", tempfile.mkdtemp(prefix="nodl-"), {}))

    def test_setup_asset_is_the_plugin_copy(self):
        self.assertEqual((PLUGIN / "rules/clarifying-questions.md").read_text(encoding="utf-8"),
                         ASSET.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
