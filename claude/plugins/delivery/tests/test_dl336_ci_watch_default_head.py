"""DL336: ci_watch head_of ignores origin/HEAD and the default branch, so no train is made for it.
Temp git repo (bare remote + clone) and temp ledger; no network."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SHARED))

import ci_watch as cw  # noqa: E402

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **ENV})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def make_repo(tmp, default):
    bare = Path(tmp) / "remote.git"
    git(tmp, "init", "-q", "--bare", "-b", default, str(bare))
    clone = Path(tmp) / "clone"
    git(tmp, "clone", "-q", str(bare), str(clone))
    git(clone, "checkout", "-q", "-B", default)
    (clone / "a.txt").write_text("a")
    git(clone, "add", ".")
    git(clone, "commit", "-q", "-m", "one")
    git(clone, "push", "-q", "-u", "origin", default)
    git(clone, "remote", "set-head", "origin", default)
    return clone


class DefaultHead(unittest.TestCase):
    def check(self, default):
        with tempfile.TemporaryDirectory() as tmp:
            clone = make_repo(tmp, default)
            sha = git(clone, "rev-parse", "HEAD")
            cwd = os.getcwd()
            os.chdir(clone)
            try:
                self.assertEqual(cw.head_of(sha, None), (None, None))
                git(clone, "checkout", "-q", "-b", "feat-x")
                (clone / "b.txt").write_text("b")
                git(clone, "add", ".")
                git(clone, "commit", "-q", "-m", "two")
                feat = git(clone, "rev-parse", "HEAD")
                self.assertEqual(cw.head_of(feat, None), ("feat-x", None))
                self.assertEqual(cw.head_of(sha, None), (None, None))
            finally:
                os.chdir(cwd)

    def test_main(self):
        self.check("main")

    def test_trunk(self):
        self.check("trunk")

    def test_config_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = make_repo(tmp, "main")
            git(clone, "checkout", "-q", "-b", "develop")
            (clone / "d.txt").write_text("d")
            git(clone, "add", ".")
            git(clone, "commit", "-q", "-m", "dev")
            git(clone, "push", "-q", "origin", "develop")
            sha = git(clone, "rev-parse", "HEAD")
            (clone / ".delivery").mkdir()
            (clone / ".delivery" / "config.json").write_text(json.dumps({"default_branch": "develop"}))
            cwd = os.getcwd()
            os.chdir(clone)
            try:
                with mock.patch.object(cw, "ledger_root", return_value=clone):
                    self.assertEqual(cw.head_of(sha, None), (None, None))
            finally:
                os.chdir(cwd)

    def test_ledger_ci_makes_no_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = make_repo(tmp, "main")
            sha = git(clone, "rev-parse", "HEAD")
            calls = []

            def rec(root, op, **kw):
                calls.append(kw)
                return False

            cwd = os.getcwd()
            os.chdir(clone)
            try:
                import delivery_common as dc
                with mock.patch.object(cw, "ledger_root", return_value=clone), \
                        mock.patch.object(dc, "ledger_record", side_effect=rec):
                    cw.ledger_ci(sha, "green")
            finally:
                os.chdir(cwd)
            self.assertEqual(len(calls), 1)
            self.assertIsNone(calls[0]["branch"])
            self.assertFalse(calls[0]["create"])


if __name__ == "__main__":
    unittest.main()
