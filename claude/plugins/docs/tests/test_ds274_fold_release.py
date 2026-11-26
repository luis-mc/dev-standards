"""DS274: docs_fold.py fold --release folds only the notes of that release's tasks (R5.27)."""
import contextlib
import io
import json
import unittest

from _helpers import *  # noqa
import docs_fold as F


def two_notes():
    d = project({"docs/features/import/spec.md": spec(version="1.3.1", body="# T\n"),
                 "docs/features/export/spec.md": spec(version="2.0.0", body="# E\n")})
    reg = d / "docs" / "project"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "registry.json").write_text(json.dumps({"tasks": [{"id": "T1", "release": 1}, {"id": "T2", "release": 2}]}))
    F.main(["note", "--root", str(d), "--doc", "features/import", "--task", "T1", "--change", "minor", "--text", "one"])
    F.main(["note", "--root", str(d), "--doc", "features/export", "--task", "T2", "--change", "minor", "--text", "two"])
    return d


def fold(d, *extra):
    with contextlib.redirect_stdout(io.StringIO()):
        return F.main(["fold", "--release", "RELEASE-1", "--root", str(d), *extra])


class FoldReleaseTests(unittest.TestCase):
    def test_release_one_leaves_release_two_pending(self):
        d = two_notes()
        self.assertEqual(fold(d), 0)
        self.assertEqual(list(F.find_notes(d)), ["docs/features/export/spec.md"])

    def test_all_folds_both(self):
        d = two_notes()
        self.assertEqual(fold(d, "--all"), 0)
        self.assertEqual(F.find_notes(d), {})

    def test_no_record_folds_both(self):
        d = two_notes()
        (d / "docs" / "project" / "registry.json").unlink()
        fold(d)
        self.assertEqual(F.find_notes(d), {})

    def test_unknown_task_is_folded(self):
        d = two_notes()
        (d / "docs" / "project" / "registry.json").write_text(json.dumps({"tasks": [{"id": "T2", "release": 2}]}))
        fold(d)
        self.assertEqual(list(F.find_notes(d)), ["docs/features/export/spec.md"])


if __name__ == "__main__":
    unittest.main()
