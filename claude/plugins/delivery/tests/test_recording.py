import json
import os
import unittest
from pathlib import Path
from unittest import mock

from _helpers import L, make_root  # noqa: F401  (puts scripts/ on sys.path)
import hook_stop as S
import hooklib as H

MERGE = "m" * 40


def train(tid="T-1", pr=42, **kw):
    t = {"id": tid, "release_no": 41, "branch": "release/41", "pr": pr, "state": "merged",
         "merged_at": "2026-10-20T01:00:00Z", "cleaned_at": None, "live_at": None, "smoke": {"state": None, "at": None},
         "cargo": [{"task": "DV1", "branch": "DV1-fix"}], "ci": {"state": "success", "head_sha": "abc"}}
    t.update(kw)
    return t


def seed(root, *trains):
    L.update(root, lambda led: led["trains"].extend(trains))


def stub_gh(runs, merge=MERGE, view=None):
    def run(argv, root, timeout=60):
        if argv[:3] == ["gh", "pr", "view"]:
            return (0, json.dumps({"mergeCommit": {"oid": merge} if merge else None}))
        if argv[:3] == ["gh", "run", "list"]:
            assert argv[argv.index("--workflow") + 1] == (view or "Production smoke")
            return (0, json.dumps(runs))
        if argv[:3] == ["gh", "run", "view"]:
            return (0, json.dumps(runs[0])) if runs else (1, "")
        return (1, "")
    return run


def srun(i, conclusion="success", status="completed", at="2026-10-20T02:00:00Z"):
    return {"databaseId": i, "status": status, "conclusion": conclusion, "createdAt": at,
            "url": "https://github.com/o/r/actions/runs/%d" % i}


class Args:
    def __init__(self, **kw):
        self.run = None
        self.__dict__.update(kw)


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        seed(self.root, train(), train("T-2"), train("T-3", pr=486))

    def rows(self):
        return {t["id"]: t for t in L.load(self.root)["trains"]}

    def test_success_records_every_row_with_the_pr(self):
        before = json.dumps(self.rows()["T-1"]["ci"])
        code = L._cmd_smoke(self.root, Args(pr=42), run=stub_gh([srun(1, "failure", at="2026-10-20T01:00:00Z"), srun(2)]))
        self.assertEqual(code, 0)
        rows = self.rows()
        for tid in ("T-1", "T-2"):
            self.assertEqual(rows[tid]["smoke"]["state"], "pass")
            self.assertTrue(rows[tid]["smoke"]["at"])
            self.assertTrue(rows[tid]["smoke"]["run"].endswith("/2"))
            self.assertTrue(rows[tid]["live_at"])
            self.assertEqual(rows[tid]["state"], "live")
        self.assertIsNone(rows["T-3"]["smoke"]["state"])
        self.assertEqual(json.dumps(rows["T-1"]["ci"]), before)
        self.assertIn("smoke.pass", [e["kind"] for e in L.load(self.root)["events"]])

    def test_failure_records_fail_and_exits_1(self):
        self.assertEqual(L._cmd_smoke(self.root, Args(pr=42), run=stub_gh([srun(3, "failure")])), 1)
        self.assertEqual(self.rows()["T-1"]["smoke"]["state"], "fail")

    def test_missing_or_unfinished_records_nothing(self):
        for runs, merge in (([], MERGE), ([srun(4, None, "in_progress")], MERGE), ([], None)):
            self.assertEqual(L._cmd_smoke(self.root, Args(pr=42), run=stub_gh(runs, merge)), 1)
            self.assertIsNone(self.rows()["T-1"]["smoke"]["state"])
            self.assertEqual(L.load(self.root)["events"], [])

    def test_explicit_run_and_configured_workflow(self):
        self.assertEqual(L._cmd_smoke(self.root, Args(pr=42, run="https://github.com/o/r/actions/runs/9"),
                                      run=stub_gh([srun(9)])), 0)
        root = make_root({"smoke_workflow": "Prod check"})
        seed(root, train())
        self.assertEqual(L._cmd_smoke(root, Args(pr=42), run=stub_gh([srun(5)], view="Prod check")), 0)

    def test_unknown_pr(self):
        with self.assertRaises(L.LedgerError):
            L._cmd_smoke(self.root, Args(pr=1), run=stub_gh([]))


def git_stub(remote=(), worktrees=()):
    def run(argv, root, timeout=60):
        if argv[:3] == ["git", "ls-remote", "--heads"]:
            return (0, "sha\trefs/heads/%s\n" % argv[-1] if argv[-1] in remote else "")
        if argv[:3] == ["git", "worktree", "list"]:
            return (0, "".join("worktree /w/%s\nHEAD x\nbranch refs/heads/%s\n\n" % (b, b) for b in worktrees))
        return (1, "")
    return run


class CleanedTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        seed(self.root, train(), train("T-2"))

    def rows(self):
        return {t["id"]: t for t in L.load(self.root)["trains"]}

    def test_present_branches_and_worktrees_are_listed_and_nothing_recorded(self):
        for kw in ({"remote": ["DV1-fix"]}, {"worktrees": ["release/41"]}):
            self.assertEqual(L._cmd_cleaned(self.root, Args(pr=42), run=git_stub(**kw)), 1)
            self.assertIsNone(self.rows()["T-1"]["cleaned_at"])
        self.assertEqual(L.load(self.root)["events"], [])

    def test_gone_records_every_row_and_an_event(self):
        self.assertEqual(L._cmd_cleaned(self.root, Args(pr=42), run=git_stub()), 0)
        for t in self.rows().values():
            self.assertTrue(t["cleaned_at"])
            self.assertEqual(t["state"], "cleaned")
        self.assertIn("cleaned", [e["kind"] for e in L.load(self.root)["events"]])

    def test_git_failure_records_nothing(self):
        with self.assertRaises(L.LedgerError):
            L._cmd_cleaned(self.root, Args(pr=42), run=lambda a, r, timeout=60: (1, ""))
        self.assertIsNone(self.rows()["T-1"]["cleaned_at"])


class MessageTests(unittest.TestCase):
    def test_messages_name_configured_commands_then_the_recorder(self):
        led = {"trains": [train()]}
        cfg = H.load_config(make_root({"cleanup_command": "python scripts/delivery/cleanup.py --pr {pr}",
                                       "smoke_command": "scripts/smoke.sh {pr}"}))
        cfg.update({"cleanup_command": "python scripts/delivery/cleanup.py --pr {pr}", "smoke_command": "scripts/smoke.sh {pr}"})
        msgs = dict(S.check_trains(dict(led, agents=[]), cfg, H.now()))
        m14, m18 = msgs["DL-14:T-1"], msgs["DL-18:T-1"]
        self.assertIn("`python scripts/delivery/cleanup.py --pr 42`", m14)
        self.assertIn("delivery_ledger.py cleaned --pr 42", m14)
        self.assertIn("`scripts/smoke.sh 42`", m18)
        self.assertIn("delivery_ledger.py smoke --pr 42", m18)
        self.assertTrue(os.path.isabs(m14.split("`python ")[-1].split(" ")[0]))

    def test_defaults_without_config(self):
        msgs = dict(S.check_trains({"trains": [train()], "agents": []}, H.load_config(make_root()), H.now()))
        self.assertIn("Run cleanup.py --pr 42", msgs["DL-14:T-1"])
        self.assertIn("delivery_ledger.py smoke --pr 42", msgs["DL-18:T-1"])


class LoopLimitTests(unittest.TestCase):
    def setUp(self):
        self.root = str(make_root())
        self.led = {"trains": [train()], "agents": []}
        self.found = [("DL-14:T-1", "DL-14 RELEASE-41 is merged and not cleaned. x")]

    def turn(self, found=None, led=None, limit=3, sid="s"):
        return S.repeat_limit(self.found if found is None else found, led or self.led, self.root, sid, limit)

    def test_three_blocks_then_one_notice_then_silence(self):
        for _ in range(3):
            blocking, noticed = self.turn()
            self.assertEqual((len(blocking), noticed), (1, []))
        blocking, noticed = self.turn()
        self.assertEqual((blocking, len(noticed)), ([], 1))
        self.assertIn("still open after 3 tries", S.limit_notice(noticed, 3))
        self.assertIn("RELEASE-41", S.limit_notice(noticed, 3))
        self.assertEqual(self.turn(), ([], []))

    def test_field_change_or_new_finding_blocks_again(self):
        for _ in range(4):
            self.turn()
        changed = {"trains": [train(cleaned_at="2026-10-20T03:00:00Z")], "agents": []}
        blocking, _ = self.turn(led=changed)
        self.assertEqual(len(blocking), 1)
        for _ in range(4):
            self.turn()
        new = self.found + [("DL-18:T-1", "DL-18 RELEASE-41 is merged and x")]
        blocking, noticed = self.turn(found=new)
        self.assertEqual([k for k, _ in blocking], ["DL-18:T-1"])
        self.assertEqual(noticed, [])

    def test_zero_never_limits_and_sessions_are_separate(self):
        for _ in range(6):
            self.assertEqual(len(self.turn(limit=0)[0]), 1)
        for _ in range(4):
            self.turn()
        self.assertEqual(len(self.turn(sid="other")[0]), 1)

    def test_limit_config_reading(self):
        self.assertEqual(H.repeat_limit({}), 3)
        self.assertEqual(H.repeat_limit({"stop_repeat_limit": 0}), 0)
        self.assertEqual(H.repeat_limit({"stop_repeat_limit": "x"}), 3)


class StopMainTests(unittest.TestCase):
    def test_main_blocks_three_times_then_notices_once(self):
        import io, contextlib
        root = make_root()
        seed(root, train())
        outs = []
        for _ in range(5):
            buf = io.StringIO()
            with mock.patch.object(S.H, "read_input", return_value={"cwd": str(root), "session_id": "z"}), \
                    mock.patch.object(S, "check_one_ci_per_release", return_value=[]), \
                    contextlib.redirect_stdout(buf):
                S.main()
            outs.append(buf.getvalue().strip())
        self.assertTrue(all('"block"' in o for o in outs[:3]))
        self.assertIn("still open after 3 tries", outs[3])
        self.assertNotIn('"block"', outs[3])
        self.assertEqual(outs[4], "")


if __name__ == "__main__":
    unittest.main()
