"""DS252: a real fold prints the Full Progress publish steps when the page is stale; a dry run and a failed check stay quiet."""
import contextlib
import io
import unittest
from unittest import mock

from _helpers import *  # noqa
import docs_fold as F


def run(d, stale, *extra):
    note_args = ["note", "--root", str(d), "--doc", "features/import", "--task", "T1", "--change", "minor", "--text", "x"]
    F.main(note_args)
    out = io.StringIO()
    with mock.patch.object(F, "full_progress_stale", return_value=stale), contextlib.redirect_stdout(out):
        code = F.main(["fold", "--release", "RELEASE-1", "--root", str(d), *extra])
    return code, out.getvalue()


def proj():
    return project({"docs/features/import/spec.md": spec(version="1.3.1", body="# T\n")})


class StaleNoticeTests(unittest.TestCase):
    def test_notice_after_real_fold_when_stale(self):
        code, out = run(proj(), True)
        self.assertEqual(code, 0)
        self.assertIn("Full Progress is stale", out)

    def test_quiet_when_not_stale(self):
        self.assertNotIn("Full Progress is stale", run(proj(), False)[1])

    def test_quiet_on_dry_run(self):
        self.assertNotIn("Full Progress is stale", run(proj(), True, "--dry-run")[1])

    def test_no_record_means_not_stale(self):
        self.assertFalse(F.full_progress_stale(proj()))


if __name__ == "__main__":
    unittest.main()
