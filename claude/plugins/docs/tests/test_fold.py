import unittest
from _helpers import *  # noqa
import docs_fold as F
import docs_lib as D


def proj():
    return project({
        "docs/features/import/spec.md": spec(version="1.3.1", body="# T\n"),
        "docs/architecture/sec.md": "---\nid: sec\ntitle: Sec\nversion: 0.1.0\n---\n# Sec\n",
    })


def note(d, doc, task, change, text, **kw):
    args = ["note", "--root", str(d), "--doc", doc, "--task", task, "--change", change, "--text", text]
    for k, v in kw.items():
        args += ([f"--{k}"] if v is True else [f"--{k}", v])
    return F.main(args)


class FoldTests(unittest.TestCase):
    def test_note_paths(self):
        d = proj()
        self.assertEqual(note(d, "features/import", "IW21", "minor", "Step 3 shows sure matches first.", section="3"), 0)
        self.assertEqual(note(d, "architecture/sec", "SEC1", "patch", "Wording."), 0)
        self.assertIn("change: minor", r(d, "docs/features/import/changes/IW21.md"))
        self.assertIn('section: "3"', r(d, "docs/features/import/changes/IW21.md"))
        self.assertTrue((d / "docs/architecture/changes/sec/SEC1.md").is_file())

    def test_note_refuses_unknown_doc_duplicate_and_multiline(self):
        d = proj()
        self.assertEqual(note(d, "features/nope", "T", "minor", "x"), 2)
        self.assertEqual(note(d, "features/import", "T1", "minor", "x"), 0)
        self.assertEqual(note(d, "features/import", "T1", "minor", "y"), 2)
        self.assertEqual(note(d, "features/import", "T2", "minor", "a\nb"), 2)

    def test_one_version_per_release_highest_wins(self):
        d = proj()
        note(d, "features/import", "IW21", "minor", "Step 3 shows sure matches first.", section="3")
        note(d, "features/import", "IW23", "patch", "New limit: 500 files, ceiling 2000 (R6.3).")
        note(d, "features/import", "IW24", "patch", "Pipe | in text.")
        self.assertEqual(F.main(["fold", "--root", str(d), "--release", "RELEASE-131", "--date", "2026-10-31"]), 0)
        t = r(d, "docs/features/import/spec.md")
        fm, _b, _ = D.parse_front_matter(t)
        self.assertEqual(fm["version"], "1.4.0", "minor wins over patch, patch resets")
        rows = [l for l in t.split("\n") if l.startswith("| 1.4.0")]
        self.assertEqual(len(rows), 1, "one row for the release")
        self.assertIn("RELEASE-131", rows[0])
        self.assertIn("IW21, IW23, IW24", rows[0])
        self.assertIn("(section 3)", rows[0])
        self.assertIn("Pipe \\| in text", rows[0])
        self.assertIn("<br>", rows[0])
        self.assertFalse((d / "docs/features/import/changes").exists(), "folded notes are consumed")

    def test_breaking_is_major_and_table_is_newest_first(self):
        d = proj()
        note(d, "features/import", "A1", "minor", "first")
        F.main(["fold", "--root", str(d), "--release", "R1", "--date", "2026-10-01"])
        note(d, "features/import", "A2", "minor", "gone", breaking=True)
        F.main(["fold", "--root", str(d), "--release", "R2", "--date", "2026-10-02"])
        t = r(d, "docs/features/import/spec.md")
        self.assertEqual(D.parse_front_matter(t)[0]["version"], "2.0.0")
        self.assertLess(t.index("| 2.0.0"), t.index("| 1.4.0"))
        self.assertEqual(t.count("## Versions"), 1)

    def test_patch_only(self):
        d = proj()
        note(d, "architecture/sec", "S1", "patch", "typo")
        F.main(["fold", "--root", str(d), "--release", "R1"])
        self.assertEqual(D.parse_front_matter(r(d, "docs/architecture/sec.md"))[0]["version"], "0.1.1")

    def test_dry_run_changes_nothing(self):
        d = proj()
        note(d, "features/import", "A1", "minor", "first")
        before = r(d, "docs/features/import/spec.md")
        F.main(["fold", "--root", str(d), "--release", "R1", "--dry-run"])
        self.assertEqual(r(d, "docs/features/import/spec.md"), before)
        self.assertTrue((d / "docs/features/import/changes/A1.md").is_file())

    def test_note_for_missing_doc_is_an_error_and_kept(self):
        d = proj()
        w(d, "docs/features/ghost/changes/X.md", "---\nchange: minor\n---\nx\n")
        self.assertEqual(F.main(["fold", "--root", str(d), "--release", "R1"]), 2)
        self.assertTrue((d / "docs/features/ghost/changes/X.md").is_file())

    def test_pending(self):
        d = proj()
        self.assertEqual(F.main(["pending", "--root", str(d)]), 0)
        note(d, "features/import", "A1", "minor", "x")
        self.assertEqual(F.main(["pending", "--root", str(d)]), 1)
        F.main(["fold", "--root", str(d), "--release", "R1"])
        self.assertEqual(F.main(["pending", "--root", str(d)]), 0)

    def test_fold_removes_tracked_notes_with_git(self):
        d = proj()
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "i")
        note(d, "features/import", "A1", "minor", "x")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "n")
        F.main(["fold", "--root", str(d), "--release", "R1"])
        self.assertIn("D  docs/features/import/changes/A1.md", git(d, "status", "--porcelain").stdout)

    def test_bump(self):
        self.assertEqual(F.bump("1.2.3", "major"), "2.0.0")
        self.assertEqual(F.bump("1.2.3", "minor"), "1.3.0")
        self.assertEqual(F.bump("1.2.3", "patch"), "1.2.4")
        self.assertEqual(F.bump("", "minor"), "0.1.0")


if __name__ == "__main__":
    unittest.main()
