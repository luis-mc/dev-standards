"""DL303: agent liveness from the branch's last commit, and owns overlap warnings. Fake git/gh; no network."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _helpers import make_root, L  # noqa: E402
import hook_stop  # noqa: E402,F401  (import check only)


def ledger(root):
    return json.loads((Path(root) / ".delivery" / "ledger.json").read_text())


def seed(root, agents=(), trains=()):
    L.update(root, lambda led: (led["agents"].extend(agents), led["trains"].extend(trains)))


class FakeRun:
    """Replaces L._run_cmd. `remote` is the ls-remote output, `gh` the API date or None for a failure."""
    def __init__(self, remote="abc\trefs/heads/B\n", gh=None, log=None):
        self.remote, self.gh, self.log = remote, gh, log

    def __call__(self, argv, root, timeout=25):
        if argv[:2] == ["git", "ls-remote"]:
            return self.remote
        if argv[0] == "gh":
            return self.gh
        if argv[:2] == ["git", "fetch"]:
            return "" if self.log else None
        if argv[:2] == ["git", "log"]:
            return self.log
        return None


class Base(unittest.TestCase):
    def setUp(self):
        self._orig = L._run_cmd

    def tearDown(self):
        L._run_cmd = self._orig

    def check(self, fake, last_event=None):
        L._run_cmd = fake
        root = make_root()
        seed(root, [{"id": "a1", "task": "T1", "branch": "B", "state": "running"}])
        argv = ["--root", str(root), "agent-check", "T1"] + (["--last-event-at", last_event] if last_event else [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(L.main(argv), 0)
        return ledger(root)["agents"][0]


class Liveness(Base):
    def test_branch_commit_newer_wins(self):
        a = self.check(FakeRun(gh="2026-11-13T10:30:00Z"), "2026-11-13T10:00:00Z")
        self.assertEqual((a["liveness_source"], a["liveness_at"]), ("branch", "2026-11-13T10:30:00Z"))

    def test_no_branch_uses_last_event_at(self):
        a = self.check(FakeRun(remote="", gh="2026-11-13T10:30:00Z"), "2026-11-13T10:00:00Z")
        self.assertEqual((a["liveness_source"], a["liveness_at"]), ("last_event_at", "2026-11-13T10:00:00Z"))

    def test_gh_failure_uses_last_event_at(self):
        a = self.check(FakeRun(gh=None), "2026-11-13T10:00:00Z")
        self.assertEqual((a["liveness_source"], a["liveness_at"]), ("last_event_at", "2026-11-13T10:00:00Z"))

    def test_git_log_when_gh_fails(self):
        a = self.check(FakeRun(gh=None, log="2026-11-13T12:30:00+02:00\n"))
        self.assertEqual((a["liveness_source"], a["liveness_at"]), ("branch", "2026-11-13T10:30:00Z"))

    def test_nothing_known(self):
        a = self.check(FakeRun(remote="", gh=None))
        self.assertEqual(a["liveness_source"], "none")
        self.assertNotIn("liveness_at", a)

    def test_stop_hook_uses_liveness(self):
        H = hook_stop.H
        at = H.parse_ts("2026-11-13T11:00:00Z")
        cfg = {"check_min": 30}
        base = {"id": "a1", "task": "T1", "state": "running", "started": "2026-11-13T09:00:00Z",
                "eta": {"breakdown": {"work": 1}}}
        led = {"agents": [dict(base)]}
        self.assertTrue(any("was not checked" in m for _, m in hook_stop.check_agents(led, cfg, at)))
        led = {"agents": [dict(base, liveness_at="2026-11-13T10:50:00Z")]}
        self.assertFalse(any("was not checked" in m for _, m in hook_stop.check_agents(led, cfg, at)))


class Owns(unittest.TestCase):
    def eta(self, root, agent, owns):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = L.main(["--root", str(root), "agent-eta", agent, "--setup", "1", "--work", "1", "--checks", "1",
                         "--owns", owns])
        self.assertEqual(rc, 0)
        return err.getvalue()

    def two(self, other_owns, mine, other_state="running", trains=()):
        root = make_root()
        seed(root, [{"id": "a1", "task": "T1", "state": other_state, "owns": other_owns},
                    {"id": "a2", "task": "T2", "state": "running"}], trains)
        return root, self.eta(root, "a2", mine)

    def test_same_path_warns_with_name(self):
        root, out = self.two("x/a.py (new), docs/b.md", "x/a.py")
        self.assertIn("WARNING", out)
        self.assertIn("T1", out)
        self.assertIn("x/a.py", out)
        self.assertEqual(ledger(root)["agents"][1]["owns"], "x/a.py")

    def test_prefix_overlap(self):
        _, out = self.two("x/scripts/", "x/scripts/a.py")
        self.assertIn("x/scripts", out)
        _, out = self.two("x/tests/test_a_*.py", "x/tests/test_a_one.py, y/<doc>/z.md")
        self.assertIn("T1", out)

    def test_no_overlap_silent(self):
        _, out = self.two("x/a.py, x/ab/", "x/b.py, x/a.pyc2/c, docs/<feat>/n.md (note, more)")
        self.assertEqual(out, "")

    def test_done_and_joined_not_compared(self):
        trains = [{"id": "r1", "state": "joined", "cargo": [{"task": "T1"}]}]
        _, out = self.two("x/a.py", "x/a.py", "done", trains)
        self.assertEqual(out, "")
        _, out = self.two("x/a.py", "x/a.py", "done")       # done but not joined: Built, compared
        self.assertIn("T1", out)

    def test_brief_file(self):
        root = make_root()
        seed(root, [{"id": "a1", "task": "T1", "state": "running", "owns": "x/a.py"},
                    {"id": "a2", "task": "T2", "state": "running"}])
        brief = Path(root) / "BRIEF.md"
        brief.write_text("intro owns: nothing\n```delivery\ntask: T2\nowns: x/a.py (only this)\n```\n")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            L.main(["--root", str(root), "agent-eta", "a2", "--setup", "1", "--work", "1", "--checks", "1",
                    "--brief", str(brief)])
        self.assertIn("WARNING", err.getvalue())


if __name__ == "__main__":
    unittest.main()
