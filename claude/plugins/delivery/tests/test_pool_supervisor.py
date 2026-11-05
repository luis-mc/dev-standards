"""DL64: the pool supervisor recreates missing agent users at start. No useradd is called."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_supervisor as SUP  # noqa: E402

AGENT = {"slug": "app1", "user": "r-app1"}


def fake_stat(uid, gid):
    return lambda path: SimpleNamespace(st_uid=uid, st_gid=gid)


def no_folder(path):
    raise FileNotFoundError(path)


class EnsureUserTest(unittest.TestCase):
    def setUp(self):
        self.calls, self.logs = [], []

    def run_fn(self, argv):
        self.calls.append(argv)
        return 0

    def ensure(self, exists, stat, group_exists=lambda n: False):
        return SUP.ensure_user(AGENT, "/agents", run=self.run_fn, exists=lambda u: exists,
                               group_exists=group_exists, stat=stat, log=self.logs.append)

    def test_missing_user_is_created_with_folder_ids(self):
        self.assertTrue(self.ensure(False, fake_stat(999, 999)))
        self.assertEqual(self.calls[0][:5], ["groupadd", "--system", "--gid", "999", "r-app1"])
        self.assertEqual(self.calls[1][0], "useradd")
        self.assertIn("999", self.calls[1])
        self.assertEqual(self.calls[1][self.calls[1].index("--uid") + 1], "999")
        self.assertEqual(self.calls[1][self.calls[1].index("--home-dir") + 1], "/agents/app1")

    def test_existing_group_is_not_recreated(self):
        self.ensure(False, fake_stat(999, 998), group_exists=lambda n: True)
        self.assertEqual([c[0] for c in self.calls], ["useradd"])

    def test_existing_user_calls_nothing(self):
        self.assertTrue(self.ensure(True, fake_stat(999, 999)))
        self.assertEqual(self.calls, [])

    def test_missing_folder_is_skipped_with_log(self):
        self.assertFalse(self.ensure(False, no_folder))
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.logs), 1)
        self.assertIn("missing", self.logs[0])


class BackoffTest(unittest.TestCase):
    def test_missing_user_backs_off_and_logs_once(self):
        import json, tempfile, os
        d = tempfile.mkdtemp()
        f = os.path.join(d, "agents.json")
        json.dump({"agents": [AGENT]}, open(f, "w"))
        now = [100.0]
        spawned = []
        sup = SUP.Supervisor(f, d, spawn=lambda a: spawned.append(a), clock=lambda: now[0], ensure=lambda a: False)
        out = []
        orig = SUP._log
        SUP._log = out.append
        try:
            for _ in range(3):
                sup.tick()
                now[0] += 1000
        finally:
            SUP._log = orig
        self.assertEqual(spawned, [])
        self.assertEqual(len(out), 1)
        sup.tick()
        before = sup.state["app1"]["next"]
        now[0] = before - 1
        sup.tick()
        self.assertEqual(sup.state["app1"]["next"], before)


if __name__ == "__main__":
    unittest.main()
