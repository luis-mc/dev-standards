"""DS274: change_notes.py fold --release takes only the notes of that release's tasks (DL-128)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"))
import change_notes as N  # noqa: E402

REG = {"tasks": [{"id": "T1", "release": 1}, {"id": "T2", "release": 2}, {"id": "T3", "rides": "T1"}]}


def note(path, spec, task_file):
    (path / "docs" / "specs" / "changes").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "specs" / "changes" / task_file).write_text(
        "---\nspec: docs/specs/a.md\nchange: minor\n---\nChange %s.\n" % task_file, encoding="utf-8")


class ReleaseFoldTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ds274-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "docs" / "project").mkdir(parents=True)
        (self.root / "docs" / "project" / "registry.json").write_text(json.dumps(REG))
        note(self.root, "a", "T1-one.md")
        note(self.root, "a", "T2-two.md")
        note(self.root, "a", "T3-rider.md")
        note(self.root, "a", "ZZ9-unknown.md")
        self.notes, _ = N.read_notes(self.root, {"notes_dir": "docs/specs/changes"})

    def names(self, release):
        return sorted(n.path.rsplit("/", 1)[-1] for n in N.notes_of_release(self.root, self.notes, release))

    def test_release_one_leaves_release_two_pending(self):
        self.assertEqual(self.names("RELEASE-1"), ["T1-one.md", "T3-rider.md", "ZZ9-unknown.md"])
        self.assertEqual(self.names("RELEASE-2"), ["T2-two.md", "ZZ9-unknown.md"])

    def test_no_record_keeps_every_note(self):
        (self.root / "docs" / "project" / "registry.json").unlink()
        self.assertEqual(len(self.names("RELEASE-1")), 4)


if __name__ == "__main__":
    unittest.main()
