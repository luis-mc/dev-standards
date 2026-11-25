"""DP16: merge mode. auto (default) merges on green; manual leaves the merge to the owner."""
import unittest

import _helpers  # noqa: F401  (sets the script path)

import delivery_config as C
import hook_pre_tool as P
import hooklib as H
import delivery_ci_setup as S


def merge_denied(cfg, cmd="gh pr merge 5 --merge"):
    try:
        for seg in H.segments(cmd):
            P.check_merge(".", seg, {"trains": []}, cfg)
    except P.Deny as d:
        return str(d)
    return None


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
        msg = merge_denied({"watcher": {"merge_mode": "manual"}})
        self.assertIn("merge mode is manual", msg or "")

    def test_auto_does_not_trip_the_mode_check(self):
        msg = merge_denied({"watcher": {"merge_mode": "auto"}}) or ""
        self.assertNotIn("merge mode is manual", msg)


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
