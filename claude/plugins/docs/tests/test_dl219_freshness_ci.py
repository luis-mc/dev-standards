"""DL219: T2 gives the same answer in a full clone, a shallow clone, with a merge commit, and across time zones."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from _helpers import *  # noqa
import docs_check as C

SPEC = spec(code="[src/**]").replace("last_verified: 2026-10-30", "last_verified: 2026-01-01")


def commit(d, msg, when, tz="+0000", merge=False):
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{when} {tz}", GIT_AUTHOR_DATE=f"{when} {tz}")
    git(d, "add", "-A")
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg],
                   env=env, check=True, capture_output=True)


def merge(d, branch, when):
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{when} +0000", GIT_AUTHOR_DATE=f"{when} +0000")
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t", "merge", "--no-ff", "-q", "-m", "merge", branch],
                   env=env, check=True, capture_output=True)


def t2(d):
    return [x for x in C.check_freshness(Path(d), {"stale_days": 100000}) if x["code"] == "T2"]


def shallow(d, depth):
    dst = tempfile.mkdtemp(prefix="docs-sh-")
    subprocess.run(["git", "clone", "-q", "--depth", str(depth), "file://" + str(d), dst + "/c"], check=True, capture_output=True)
    return dst + "/c"


def base_repo(code_when, doc_when, code_tz="+0000", doc_tz="+0000"):
    d = make_repo(commit=False)
    w(d, "docs/features/import/spec.md", SPEC)
    commit(d, "doc", doc_when, doc_tz)
    w(d, "src/a.py", "x=1\n")
    commit(d, "code", code_when, code_tz)
    return d


class Dl219Tests(unittest.TestCase):
    def test_real_code_after_doc_warns(self):
        d = base_repo("2026-11-11T12:00:00", "2026-11-10T12:00:00")
        self.assertEqual(len(t2(d)), 1)

    def test_same_day_is_quiet(self):
        d = base_repo("2026-11-10T15:00:00", "2026-11-10T09:00:00")
        self.assertEqual(t2(d), [])

    def test_time_zone_does_not_cross_midnight(self):
        # same UTC day (10th); local dates would read 11th (+1400) vs 10th (-1000)
        d = base_repo("2026-11-11T01:00:00", "2026-11-09T15:00:00", code_tz="+1400", doc_tz="-1000")
        self.assertEqual(t2(d), [])
        d = base_repo("2026-11-11T01:00:00", "2026-11-10T20:00:00", code_tz="+1400", doc_tz="-1000")  # UTC: code 10th, doc 11th
        self.assertEqual(t2(d), [])

    def test_merge_commit_ignored(self):
        d = base_repo("2026-11-10T12:00:00", "2026-11-10T13:00:00")
        git(d, "checkout", "-q", "-b", "pr")
        w(d, "src/b.py", "y=1\n")
        commit(d, "pr", "2026-11-10T14:00:00")
        git(d, "checkout", "-q", "main")
        w(d, "src/a.py", "x=2\n")
        commit(d, "main", "2026-11-10T14:30:00")
        merge(d, "pr", "2026-11-12T10:00:00")
        self.assertEqual(t2(d), [])  # code last changed 11-10 by a real commit
        self.assertEqual(C.last_commit_date(d, ["src/**"]), "2026-11-10")

    def test_shallow_is_skipped_and_full_agrees(self):
        d = base_repo("2026-11-11T12:00:00", "2026-11-10T12:00:00")
        full = len(t2(d))
        for depth in (1, 2):
            s = shallow(d, depth)
            self.assertEqual(t2(s), [])
        self.assertEqual(full, 1)

    def test_shallow_flag_detected(self):
        d = base_repo("2026-11-11T12:00:00", "2026-11-10T12:00:00")
        self.assertFalse(C.is_shallow(Path(d)))
        self.assertTrue(C.is_shallow(Path(shallow(d, 1))))


if __name__ == "__main__":
    unittest.main()
