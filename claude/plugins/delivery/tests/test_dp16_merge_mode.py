"""DP16: merge mode. auto (default) merges on green; manual leaves the merge to the owner.
DS303: the watcher is the only merger, so a session's gh pr merge is refused in both modes (DL-03), and in
manual mode Q-4 and the DL-03 Stop check never push the session to merge (one warning line, said once)."""
import json
import os
import subprocess
import sys
import unittest

import _helpers  # noqa: F401  (sets the script path)

from _helpers import L, SCRIPTS, make_root
import delivery_config as C
import hook_pre_tool as P
import hook_stop as ST
import hooklib as H
import delivery_ci_setup as S

NOW = "2026-11-27T12:00:00+00:00"
LONG = "Should RELEASE-29 ship to the owner's users now, given that the smoke test passed an hour ago and CI is green?"


def merge_denied(cfg, cmd="gh pr merge 5 --merge"):
    try:
        for seg in H.segments(cmd):
            P.check_merge_role(seg, cfg)
    except P.Deny as d:
        return str(d)
    return None


def green_root(mode):
    root = make_root({"watcher": {"merge_mode": mode}})
    L.update(root, lambda led: led["trains"].append(
        {"id": "T-1", "branch": "release/29", "release_no": 29, "pr": 41, "state": "green",
         "green_at": "2026-11-27T11:00:00+00:00", "ci": {"state": "success", "head_sha": "a" * 40}}))
    return root


def hook(script, root, data):
    data = dict({"cwd": str(root), "session_id": "s1"}, **data)
    env = dict(os.environ, DELIVERY_NOW=NOW, DELIVERY_LOAD="10,10", DELIVERY_GH="false")
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / script)], input=json.dumps(data).encode(),
                       capture_output=True, env=env, timeout=60)
    out = p.stdout.decode().strip()
    return json.loads(out) if out else {}


def ask(root):
    return hook("hook_pre_tool.py", root, {"tool_name": "AskUserQuestion", "tool_input": {
        "questions": [{"question": LONG, "header": "Q", "options": [{"label": "a"}, {"label": "b"}]}]}})


class MergeModeConfig(unittest.TestCase):
    def test_default_is_auto(self):
        self.assertEqual(C.merge_mode({}), "auto")
        self.assertTrue(C.watcher_flags({})["merge_on_green"])

    def test_manual_turns_merge_on_green_off(self):
        cfg = {"watcher": {"merge_mode": "manual", "merge_on_green": True}}
        self.assertEqual(C.merge_mode(cfg), "manual")
        self.assertFalse(C.watcher_flags(cfg)["merge_on_green"])

    def test_bad_value_falls_back_to_auto(self):
        self.assertEqual(C.merge_mode({"watcher": {"merge_mode": "yolo"}}), "auto")


class MergeModeHook(unittest.TestCase):
    def test_manual_refuses_an_agent_merge(self):
        msg = merge_denied(H.load_config(str(make_root({"watcher": {"merge_mode": "manual"}}))))
        self.assertIn("DL-03 merge mode is manual", msg or "")

    def test_auto_refuses_a_session_merge_too(self):
        msg = merge_denied(H.load_config(str(make_root({"watcher": {"merge_mode": "auto"}})))) or ""
        self.assertIn("DL-03 the watcher is the only merger", msg)
        self.assertNotIn("merge mode is manual", msg)

    def test_auto_flag_is_dl05(self):
        msg = merge_denied(H.load_config(str(make_root())), "gh pr merge 5 --auto --merge") or ""
        self.assertTrue(msg.startswith("DL-05"), msg)

    def test_dl03_off_falls_back_to_the_ci_check(self):
        self.assertIsNone(merge_denied(H.load_config(str(make_root({"checks_off": ["DL-03"]})))))

    def test_hook_denies_merge_in_both_modes(self):
        for mode in ("auto", "manual"):
            with self.subTest(mode=mode):
                res = hook("hook_pre_tool.py", green_root(mode),
                           {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 41 --merge"}})
                out = res.get("hookSpecificOutput") or {}
                self.assertEqual(out.get("permissionDecision"), "deny")
                self.assertTrue(out.get("permissionDecisionReason", "").startswith("DL-03"))


class ManualModeDoesNotDeadlock(unittest.TestCase):
    """C2/E3: in manual mode the session cannot merge, so nothing may ask it to."""

    def test_q4_skips_green_prs_in_manual(self):
        res = ask(green_root("manual"))
        self.assertNotEqual((res.get("hookSpecificOutput") or {}).get("permissionDecision"), "deny", res)

    def test_q4_still_waits_for_the_watcher_in_auto(self):
        res = ask(green_root("auto"))
        out = res.get("hookSpecificOutput") or {}
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("watcher merges it", out.get("permissionDecisionReason", ""))

    def test_stop_check_is_one_warning_in_manual(self):
        cfg = H.load_config(str(green_root("manual")))
        out = ST.check_trains(L.load(green_root("manual")), cfg, H.now(), grouped=True)
        self.assertEqual([k for k, _ in out], [ST.MANUAL_KEY + "41"])
        self.assertIn("waiting for the owner to merge", out[0][1])

    def test_stop_hook_warns_once_and_never_blocks(self):
        root = green_root("manual")
        first = hook("hook_stop.py", root, {})
        self.assertNotIn("decision", first)
        self.assertIn("DL-03 green, waiting for the owner to merge", first.get("systemMessage", ""))
        second = hook("hook_stop.py", root, {})
        self.assertNotIn("decision", second)
        self.assertNotIn("waiting for the owner to merge", second.get("systemMessage", ""))

    def test_stop_hook_blocks_in_auto_without_a_merge_command(self):
        res = hook("hook_stop.py", green_root("auto"), {})
        self.assertEqual(res.get("decision"), "block")
        self.assertIn("DL-03", res.get("reason", ""))
        self.assertIn("watcher merges it", res.get("reason", ""))
        self.assertNotIn("gh pr merge", res.get("reason", ""))


class MergeModeSetup(unittest.TestCase):
    def test_setup_refuses_without_an_answer(self):
        errs = S.validate({"options": {"linux": 2}, "github_hosted": {"runner": {"linux": "x"}, "larger": False,
                                                                       "monthly_minutes_cap": None}})
        self.assertTrue(any(e.startswith("merge_mode") for e in errs))

    def test_setup_writes_the_answer(self):
        cfg = S.apply_answers({}, {"merge_mode": "manual", "options": {"linux": 2},
                                   "github_hosted": {"runner": {"linux": "x"}, "larger": False,
                                                     "monthly_minutes_cap": None}})
        self.assertEqual(cfg["watcher"]["merge_mode"], "manual")


if __name__ == "__main__":
    unittest.main()
