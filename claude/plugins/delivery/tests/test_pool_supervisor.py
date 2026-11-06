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


class ParallelPerAgentTest(unittest.TestCase):
    """DL83: CI_MAX_PARALLEL is the pool's CPU count divided by its agents."""

    def test_division(self):
        self.assertEqual(SUP.per_agent_parallel({"POOL_CPUS_INT": "5"}, 2), 2)
        self.assertEqual(SUP.per_agent_parallel({"POOL_CPUS_INT": "5"}, 1), 5)
        self.assertEqual(SUP.per_agent_parallel({"POOL_CPUS_INT": "1"}, 3), 1)
        self.assertEqual(SUP.per_agent_parallel({"CI_MAX_PARALLEL": "6"}, 3), 2)

    def test_spawned_env_has_value(self):
        import json
        import tempfile
        import os
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "agents.json")
            with open(f, "w") as fh:
                json.dump({"agents": [{"slug": "a", "user": "ua"}, {"slug": "b", "user": "ub"}]}, fh)
            sup = SUP.Supervisor(f, d, environ={"POOL_CPUS_INT": "5", "PATH": "/bin"})
            with mock.patch.object(SUP.subprocess, "Popen") as popen:
                sup.tick()
        self.assertEqual(popen.call_count, 2)
        for call in popen.call_args_list:
            self.assertEqual(call.kwargs["env"]["CI_MAX_PARALLEL"], "2")
            self.assertEqual(call.kwargs["env"]["PATH"], "/bin")


class PrepareTmpTest(unittest.TestCase):
    def test_old_env_gets_only_missing_lines(self):
        import os
        import tempfile
        base = tempfile.mkdtemp()
        os.mkdir(os.path.join(base, "app1"))
        env = Path(base, "app1", ".env")
        env.write_text("A=1\nTEMP=/old\nDELIVERY_MACHINE_DIR=/machine")
        calls = []
        run = lambda argv: calls.append(argv)
        for _ in range(2):
            self.assertTrue(SUP.prepare_tmp(AGENT, base, run=run))
        lines = env.read_text().splitlines()
        tmp = os.path.join(base, "app1", "tmp")
        self.assertEqual(lines, ["A=1", "TEMP=/old", "DELIVERY_MACHINE_DIR=/machine", "TMPDIR=" + tmp, "TMP=" + tmp])
        self.assertEqual(os.stat(tmp).st_mode & 0o777, 0o700)
        self.assertIn(["chown", "r-app1:r-app1", tmp], calls)

    def test_missing_folder_does_not_block(self):
        self.assertTrue(SUP.prepare_tmp(AGENT, "/nonexistent-base", run=lambda a: None))
