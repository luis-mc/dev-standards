import unittest
from _helpers import *  # noqa
import docs_fold as F

SPEC = "# Spec\n\n**Status:** Normative\n**Version:** 1.7.0\n\n## 1. Rules\n"
FM = "---\nid: sec\ntitle: Sec\nversion: 0.1.0\n---\n# Sec\n"


def note(d, doc, task, change="minor"):
    return F.main(["note", "--root", str(d), "--doc", doc, "--task", task, "--change", change, "--text", "Changed."])


def fold(d):
    return F.main(["fold", "--root", str(d), "--release", "RELEASE-1", "--date", "2026-11-01"])


class VersionLineTests(unittest.TestCase):
    def test_version_line_bumped_in_place(self):
        d = make_repo({"docs/architecture/spec.md": SPEC})
        self.assertEqual(note(d, "architecture/spec", "T1"), 0)
        self.assertEqual(fold(d), 0)
        t = r(d, "docs/architecture/spec.md")
        self.assertIn("**Version:** 1.8.0", t)
        self.assertNotIn("1.7.0", t)
        self.assertFalse(t.startswith("---"))
        self.assertNotIn("## Versions", t)

    def test_existing_table_gets_row(self):
        d = make_repo({"docs/architecture/spec.md": SPEC + "\n## Change log\n\n| Version | Date |\n|---|---|\n| 1.7.0 | x |\n"})
        note(d, "architecture/spec", "T1", "patch")
        self.assertEqual(fold(d), 0)
        t = r(d, "docs/architecture/spec.md")
        self.assertIn("**Version:** 1.7.1", t)
        self.assertLess(t.index("| 1.7.1 |"), t.index("| 1.7.0 |"))

    def test_front_matter_doc_unchanged(self):
        d = make_repo({"docs/architecture/sec.md": FM})
        note(d, "architecture/sec", "T1")
        self.assertEqual(fold(d), 0)
        t = r(d, "docs/architecture/sec.md")
        self.assertIn("version: 0.2.0", t)
        self.assertIn("## Versions", t)

    def test_both_refuses(self):
        both = FM + "\n**Version:** 1.7.0\n"
        d = make_repo({"docs/architecture/sec.md": both})
        note(d, "architecture/sec", "T1")
        self.assertEqual(fold(d), 2)
        self.assertEqual(r(d, "docs/architecture/sec.md"), both)
        self.assertTrue((d / "docs/architecture/changes/sec/T1.md").is_file())


if __name__ == "__main__":
    unittest.main()
