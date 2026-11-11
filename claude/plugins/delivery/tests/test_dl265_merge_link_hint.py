"""DL265: the DL-06 refusal names the link command for an unlinked PR; ci_watch says when no train links the commit.
Temp ledger, stubbed gh; no network."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SHARED))

from _helpers import make_root, L  # noqa: E402
import hook_pre_tool as HP  # noqa: E402
import ci_watch as cw  # noqa: E402

SHA = "b" * 40


def fake_gh(view):
    def gh(root, args, *a, **k):
        if args[:2] == ["pr", "view"]:
            return 0, json.dumps({k2: v for k2, v in view.items() if k2 in args[-1]})
        return 1, ""
    return gh


def refusal(ledger_trains, view=None, cmd="gh pr merge 7 --squash"):
    root = make_root()
    L.update(root, lambda led: led["trains"].extend(ledger_trains))
    view = view or {"number": 7, "headRefOid": SHA, "headRefName": "feat-x"}
    seg = cmd.split()
    with mock.patch.object(HP.H, "gh", fake_gh(view)):
        try:
            HP.check_merge(root, seg, L.load(root))
        except HP.Deny as e:
            return str(e)
    return None


class Refusal(unittest.TestCase):
    def test_unlinked_pr_names_link_command(self):
        msg = refusal([])
        self.assertIn("DL-06", msg)
        self.assertIn("delivery_ledger.py link --pr 7 --sha %s --branch feat-x" % SHA, msg)
        self.assertIn("ci_watch.py %s" % SHA, msg)

    def test_placeholders_when_unreadable(self):
        msg = refusal([], view={"number": 7})
        self.assertIn("link --pr 7 --sha <head sha> --branch <head branch>", msg)

    def test_linked_not_green_keeps_old_message(self):
        msg = refusal([{"id": "t1", "pr": 7, "state": "ci", "ci": {"head_sha": SHA, "state": "running"}}])
        self.assertIn("no ledger CI success for the current head of PR 7", msg)
        self.assertNotIn("link --pr", msg)

    def test_linked_green_passes(self):
        self.assertIsNone(refusal([{"id": "t1", "pr": 7, "state": "green", "ci": {"head_sha": SHA, "state": "success"}}]))


class CiWatchHint(unittest.TestCase):
    def run_ci(self, trains, branch):
        root = make_root()
        L.update(root, lambda led: led["trains"].extend(trains))
        err = io.StringIO()
        with mock.patch.object(cw, "ledger_root", return_value=root), \
                mock.patch.object(cw, "head_of", return_value=(branch, None)), \
                contextlib.redirect_stderr(err):
            cw.ledger_ci(SHA, "success")
        return root, err.getvalue()

    def test_unlinked_commit_prints_hint(self):
        root, err = self.run_ci([], None)
        self.assertIn("ci_watch: no train in the ledger links %s; the result was not recorded; link it with "
                      "delivery_ledger.py link --pr N --sha %s --branch <branch>, then run ci_watch again" % (SHA, SHA), err)
        self.assertEqual(len(err.strip().splitlines()), 1)

    def test_linked_commit_records_silently(self):
        root, err = self.run_ci([], "feat-x")
        self.assertEqual(err, "")
        t = L.load(root)["trains"]
        self.assertEqual((t[0]["ci"]["head_sha"], t[0]["ci"]["state"]), (SHA, "success"))


if __name__ == "__main__":
    unittest.main()
