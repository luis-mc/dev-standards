"""DS270: DL-40 is enforced once (DL-126) and a PC-bound line with no PC-bound step warns (DL-127)."""
import json
import unittest

from _helpers import make_root
import hook_pre_tool as P
import hooklib as H

REG = {"tasks": [
    {"id": "AA1", "app": "web", "status": "To do"},
    {"id": "AA2", "app": "web", "status": "Waiting"},
    {"id": "AA3", "app": "web", "status": "Live"},
    {"id": "BB1", "app": "api", "status": "To do"},
    {"id": "CC1", "status": "To do"},
]}
OFF = {"brief_markers": [], "checks_off": ["DL-89", "DL-37"]}


def root_with_registry(cfg=None):
    root = make_root(dict(OFF, **(cfg or {})))
    d = root / "docs" / "project"
    d.mkdir(parents=True)
    (d / "registry.json").write_text(json.dumps(REG))
    return root


def launch(root, prompt, tool="RemoteTrigger", cfg=None):
    cfg = cfg if cfg is not None else H.load_config(str(root))
    ti = {"action": "run", "prompt": prompt} if tool == "RemoteTrigger" else {"prompt": prompt}
    notes = []
    try:
        P.check_launch(cfg, H.load_ledger(str(root)), {"tool_name": tool, "tool_input": ti},
                       "cloud" if tool == "RemoteTrigger" else "local", str(root), notes)
    except P.Deny as d:
        return str(d), notes
    return None, notes


class BundlingTests(unittest.TestCase):
    def test_denied_once_with_the_list_then_passes(self):
        root = root_with_registry()
        why, _ = launch(root, "```delivery\ntask: AA1\n```\nDo it")
        self.assertIn("DL-40", why)
        self.assertIn("AA2", why)
        self.assertNotIn("AA3", why)
        self.assertNotIn("BB1", why)
        self.assertIsNone(launch(root, "```delivery\ntask: AA1\n```\nDo it")[0])

    def test_task_read_from_prompt_text(self):
        root = root_with_registry()
        self.assertIn("DL-40", launch(root, "Task AA2 please")[0])

    def test_no_sibling_no_area_or_no_task_passes(self):
        root = root_with_registry()
        self.assertIsNone(launch(root, "Task BB1 please")[0])
        self.assertIsNone(launch(root, "Task CC1 please")[0])
        self.assertIsNone(launch(root, "no task here")[0])

    def test_checks_off(self):
        root = root_with_registry({"checks_off": ["DL-89", "DL-37", "DL-40"]})
        self.assertIsNone(launch(root, "Task AA1 please")[0])

    def test_no_record_passes(self):
        self.assertIsNone(launch(make_root(OFF), "Task AA1 please")[0])


class PcBoundTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root(dict(OFF, caps={"cloud": 50, "local": 3, "total": 53}))

    def test_reason_with_no_step_warns_and_passes(self):
        why, notes = launch(self.root, "PC-bound: it is easier\nDo it", "Agent")
        self.assertIsNone(why)
        self.assertEqual(len(notes), 1)
        self.assertIn("DL-127", notes[0])

    def test_reason_with_a_step_is_silent(self):
        why, notes = launch(self.root, "PC-bound: runs the Windows installer build\nDo it", "Agent")
        self.assertIsNone(why)
        self.assertEqual(notes, [])

    def test_no_line_still_denied(self):
        self.assertIn("DL-39", launch(self.root, "Do it", "Agent")[0])

    def test_checks_off(self):
        root = make_root(dict(OFF, checks_off=["DL-89", "DL-37", "DL-127"]))
        self.assertEqual(launch(root, "PC-bound: easier\nDo it", "Agent")[1], [])


if __name__ == "__main__":
    unittest.main()
