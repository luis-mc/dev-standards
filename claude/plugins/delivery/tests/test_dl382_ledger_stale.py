"""DL382: stale trains. No merge advice without a PR, auto-close, grouped Stop lines, close and close-stale."""
import contextlib
import io
import json
import unittest
from argparse import Namespace

from _helpers import make_root, L

import hook_stop as S  # noqa: E402
import hooklib as H  # noqa: E402


def train(tid, **kw):
    t = {"id": tid, "branch": "b-" + tid, "pr": None, "state": "green", "release_no": None, "hold": None,
         "cargo": [], "smoke": {"state": None}, "green_at": "2026-10-01T00:00:00Z", "merged_at": None,
         "cleaned_at": None, "created_at": "2026-10-01T00:00:00Z", "ci": {}}
    t.update(kw)
    return t


def seed(root, trains):
    led = L.empty_ledger()
    led["trains"] = trains
    L.write_atomic(root, led)


def gh_stub(pr_state=None, listing=None, remote="x", fail=False):
    calls = []

    def run(argv, root, timeout=60):
        calls.append(argv)
        if fail:
            return 1, ""
        if argv[:3] == ["gh", "pr", "view"]:
            return 0, json.dumps({"state": pr_state})
        if argv[:3] == ["gh", "pr", "list"]:
            return 0, json.dumps(listing or [])
        if argv[:2] == ["git", "ls-remote"]:
            return 0, remote
        return 1, ""
    run.calls = calls
    return run


def states(root):
    return {t["id"]: (t["state"], t.get("close_reason")) for t in L.load(root)["trains"]}


class Guard(unittest.TestCase):
    def test_no_train_without_branch(self):
        root = make_root()
        for bad in (None, "", "None", "HEAD"):
            with self.assertRaises(L.LedgerError):
                L.new_train(L.empty_ledger(), bad)
        L.record(root, "train_state", branch="HEAD", create=True, state="green")
        self.assertEqual(L.load(root)["trains"], [])


class Hint(unittest.TestCase):
    def test_prless_green_gets_close_hint_not_merge(self):
        led = {"trains": [train("T-1"), train("T-2")], "agents": []}
        msgs = [m for _, m in S.check_trains(led, H.load_config(make_root()), H.now(), grouped=True)]
        self.assertEqual(len(msgs), 1)
        self.assertIn("no PR", msgs[0])
        self.assertIn("close <id> --reason", msgs[0])
        self.assertNotIn("gh pr merge", msgs[0])


class Grouped(unittest.TestCase):
    def setUp(self):
        self.led = {"agents": [], "trains": [
            train(f"T-{n}", pr=n, merged_at="2026-10-02T00:00:00Z") for n in (166, 172, 176)]
            + [train("T-9", pr=9), train("T-10", pr=10)]}

    def test_one_line_per_rule(self):
        found = S.check_trains(self.led, H.load_config(make_root()), H.now(), grouped=True)
        rules = [k.split(":")[0] for k, _ in found]
        self.assertEqual(sorted(rules), ["DL-03", "DL-14", "DL-18"])
        by = {k.split(":")[0]: m for k, m in found}
        self.assertIn("DL-18 not smoke-tested (3): PRs 166, 172, 176", by["DL-18"])
        self.assertIn("smoke --pr N", by["DL-18"])
        self.assertIn("DL-14 merged and not cleaned (3): PRs 166, 172, 176", by["DL-14"])
        self.assertIn("PRs 9, 10", by["DL-03"])

    def test_ungrouped_is_per_train(self):
        found = S.check_trains(self.led, H.load_config(make_root()), H.now())
        self.assertEqual(len(found), 3 + 3 + 2)


class Auto(unittest.TestCase):
    def test_merged_elsewhere(self):
        root = make_root()
        seed(root, [train("T-1", pr=5)])
        self.assertEqual(L.autoclose(root, run=gh_stub(pr_state="MERGED")), [("T-1", "merged-elsewhere")])
        self.assertEqual(states(root)["T-1"], ("closed", "merged-elsewhere"))

    def test_prless_merged_pr_on_branch(self):
        root = make_root()
        seed(root, [train("T-1")])
        run = gh_stub(listing=[{"number": 3, "state": "MERGED"}])
        self.assertEqual(L.autoclose(root, run=run), [("T-1", "merged-elsewhere")])
        self.assertEqual(len([c for c in run.calls if c[0] == "gh"]), 1)

    def test_branch_gone(self):
        root = make_root()
        seed(root, [train("T-1", state="red")])
        self.assertEqual(L.autoclose(root, run=gh_stub(remote="")), [("T-1", "branch-gone")])
        self.assertEqual(states(root)["T-1"], ("closed", "branch-gone"))

    def test_open_pr_or_branch_present_stays(self):
        root = make_root()
        seed(root, [train("T-1"), train("T-2")])
        run = gh_stub(listing=[{"number": 3, "state": "OPEN"}], remote="")
        self.assertEqual(L.autoclose(root, run=run), [])
        self.assertEqual(L.autoclose(root, run=gh_stub(remote="abc\trefs/heads/b")), [])
        self.assertEqual(states(root)["T-1"][0], "green")

    def test_young_train_not_branch_gone(self):
        root = make_root()
        seed(root, [train("T-1", created_at=L.iso())])
        self.assertEqual(L.autoclose(root, run=gh_stub(remote="")), [])

    def test_gh_failure_changes_nothing(self):
        root = make_root()
        seed(root, [train("T-1", pr=5), train("T-2")])
        self.assertEqual(L.autoclose(root, run=gh_stub(fail=True)), [])
        self.assertEqual({v[0] for v in states(root).values()}, {"green"})

    def test_live_result_is_cached(self):
        root = make_root()
        seed(root, [train("T-1", pr=5)])
        run = gh_stub(pr_state="OPEN")
        L.autoclose(root, run=run)
        L.autoclose(root, run=run)
        self.assertEqual(len(run.calls), 1)

    def test_show_runs_autoclose_and_hook_findings(self):
        root = make_root()
        seed(root, [train("T-1", pr=5)])
        L.autoclose(root, run=gh_stub(pr_state="MERGED"))
        led = {"trains": L.load(root)["trains"], "agents": []}
        self.assertEqual(S.check_trains(led, H.load_config(root), H.now(), grouped=True), [])


class Close(unittest.TestCase):
    def run_cmd(self, root, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = L.main(["--root", str(root)] + list(argv))
        return code, out.getvalue()

    def test_close(self):
        root = make_root()
        seed(root, [train("T-1")])
        code, out = self.run_cmd(root, "close", "T-1", "--reason", "merged in another PR")
        self.assertEqual(code, 0)
        self.assertEqual(states(root)["T-1"], ("closed", "merged in another PR"))
        self.assertEqual(self.run_cmd(root, "close", "T-9", "--reason", "x")[0], 1)

    def test_close_stale_and_dry_run(self):
        root = make_root()
        seed(root, [train("T-1"), train("T-2", green_at="2026-11-10T00:00:00Z", created_at="2026-11-10T00:00:00Z",
                                        pushed_at=None),
                    train("T-3", state="cleaned")])
        code, out = self.run_cmd(root, "close-stale", "--before", "2026-11-01", "--reason", "old", "--dry-run")
        self.assertIn("would close train T-1", out)
        self.assertNotIn("T-2", out)
        self.assertEqual(states(root)["T-1"][0], "green")
        code, out = self.run_cmd(root, "close-stale", "--before", "2026-11-01", "--reason", "old")
        self.assertIn("closed train T-1", out)
        self.assertEqual(states(root)["T-1"], ("closed", "old"))
        self.assertEqual(states(root)["T-2"][0], "green")


if __name__ == "__main__":
    unittest.main()
