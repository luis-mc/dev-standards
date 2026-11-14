"""DL351 (R5.58): the ci-wait marker never blocks the gate: git runs without prompts and with a timeout."""
import importlib.util
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
SHARED = os.path.join(os.path.dirname(HERE), "templates", "shared", "scripts", "delivery")
for p in (SCRIPTS, SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)

import ci_fallback as CF  # noqa: E402
import runner_load_gate as G  # noqa: E402
import delivery_doctor as D  # noqa: E402


def fake_git(dirpath, body):
    path = os.path.join(dirpath, "git")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return dirpath


class FakeGitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def env(self, body, **extra):
        fake_git(self.tmp.name, body)
        return mock.patch.dict(os.environ, {"PATH": self.tmp.name + os.pathsep + os.environ["PATH"], **extra})

    def test_hanging_git_returns_within_timeout(self):
        with self.env("sleep 30", DELIVERY_MARKER_GIT_TIMEOUT="1"):
            t0 = time.monotonic()
            self.assertFalse(CF.claim_taken(self.tmp.name, "origin", "abc", "job"))
            self.assertFalse(CF.mark_wait(self.tmp.name, "origin", "abc", "job", "h"))
            CF.clear_wait(self.tmp.name, "origin", "abc", "job")
            self.assertLess(time.monotonic() - t0, 12)

    def test_timeout_result_is_failed(self):
        with self.env("sleep 30", DELIVERY_MARKER_GIT_TIMEOUT="1"):
            r = CF._git(self.tmp.name, "ls-remote", "origin")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("timed out", r.stderr)

    def test_env_is_noninteractive(self):
        out = os.path.join(self.tmp.name, "seen")
        with self.env('echo "$GIT_TERMINAL_PROMPT $GCM_INTERACTIVE $GIT_ASKPASS $SSH_ASKPASS|$GIT_SSH_COMMAND|$*" > %s' % out):
            env = {k: v for k, v in os.environ.items() if k not in CF.NONINTERACTIVE_ENV}
            with mock.patch.dict(os.environ, env, clear=True):
                CF._git(self.tmp.name, "ls-remote", "origin")
        seen = open(out).read()
        self.assertIn("0 never echo echo|ssh -oBatchMode=yes|", seen)
        self.assertIn("-c credential.interactive=never", seen)

    def test_set_values_are_kept(self):
        self.assertEqual(CF.noninteractive_env({"GIT_ASKPASS": "mine"})["GIT_ASKPASS"], "mine")

    def test_timeout_default_and_bad_value(self):
        with mock.patch.dict(os.environ, {"DELIVERY_MARKER_GIT_TIMEOUT": "x"}):
            self.assertEqual(CF.git_timeout(), 20.0)
        with mock.patch.dict(os.environ):
            os.environ.pop("DELIVERY_MARKER_GIT_TIMEOUT", None)
            self.assertEqual(CF.git_timeout(), 20.0)


class GateOrderTest(unittest.TestCase):
    def test_slot_taken_logged_before_claim_check(self):
        order = []

        class M:
            def stop(self):
                order.append("stop")

            def claim_lost(self):
                order.append("claim")
                return False

        lines = []
        with mock.patch.object(G.MS, "slot_label", return_value="1"):
            code, _ = G._got("lock", {"shard": "s"}, M(), 3, lambda l: (lines.append(l), order.append("log"))[0])
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("runner gate: slot 1 taken"))
        self.assertEqual(order[:3], ["log", "stop", "claim"])

    def test_marker_failure_logs_one_line_and_goes_on(self):
        lines = []
        m = G.Marker(env={}, log=lines.append)

        class Mod:
            @staticmethod
            def git_timeout():
                return 20

            @staticmethod
            def claim_taken(*a):
                raise RuntimeError("boom")

        m.mod, m.root = Mod, "."
        self.assertFalse(m.claim_lost())
        self.assertEqual(len(lines), 1)
        self.assertIn("going on", lines[0])

    def test_slow_marker_step_logs_timeout(self):
        lines = []
        m = G.Marker(env={}, log=lines.append)

        class Mod:
            @staticmethod
            def git_timeout():
                return 0.01

            @staticmethod
            def claim_taken(*a):
                time.sleep(0.05)
                return False

        m.mod, m.root = Mod, "."
        self.assertFalse(m.claim_lost())
        self.assertIn("ci-wait marker: git timed out after 0.01 s", lines[0])


class DoctorTest(unittest.TestCase):
    def runner(self, tmp, root=True):
        d = os.path.join(tmp, "runner")
        os.makedirs(d)
        if root:
            with open(os.path.join(d, ".env"), "w") as f:
                f.write("DELIVERY_MARKER_ROOT=%s\n" % tmp)
        return d

    def test_no_marker_root_no_item(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertIsNone(D.marker_credential_item(self.runner(t, root=False)))

    def test_timeout_warns_no_credential(self):
        import subprocess
        with tempfile.TemporaryDirectory() as t, \
                mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 20)):
            item = D.marker_credential_item(self.runner(t))
        self.assertEqual(item["status"], "warn")
        self.assertIn("no non-interactive git credential", item["detail"])

    def test_permission_denied_needs_admin(self):
        with tempfile.TemporaryDirectory() as t, mock.patch("subprocess.run", side_effect=PermissionError()):
            item = D.marker_credential_item(self.runner(t))
        self.assertIn(D.NEEDS_ADMIN, item["detail"])

    def test_ok_when_ls_remote_works_and_env_is_noninteractive(self):
        import subprocess
        seen = {}

        def run(argv, **kw):
            seen.update(argv=argv, **kw)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with tempfile.TemporaryDirectory() as t, mock.patch("subprocess.run", side_effect=run):
            item = D.marker_credential_item(self.runner(t))
        self.assertEqual(item["status"], "ok")
        self.assertIn("ls-remote", seen["argv"])
        self.assertEqual(seen["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(seen["timeout"], 20.0)


if __name__ == "__main__":
    unittest.main()
