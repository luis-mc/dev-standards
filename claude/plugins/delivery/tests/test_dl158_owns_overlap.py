"""DL158: the DL-41 owns overlap compares paths segment by segment and reads notes. Pure functions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hook_pre_tool as P  # noqa: E402

T = "claude/plugins/delivery/templates"


class OwnsOverlap(unittest.TestCase):
    def test_wildcard_dir_does_not_hit_other_files(self):
        a = T + "/*/scripts/delivery/gate.json (secret-scan step only)"
        self.assertFalse(P.overlaps(a, T + "/ts/scripts/delivery/mock_handler_guard.py"))
        self.assertFalse(P.overlaps(a, T + "/rust/test/x.ts"))
        self.assertTrue(P.overlaps(a, T + "/ts/scripts/delivery/gate.json"))

    def test_notes_do_not_hide_same_file(self):
        self.assertTrue(P.overlaps("docs/a/spec.md (R1.1 only)", "docs/a/spec.md (notes)"))
        self.assertTrue(P.overlaps("docs/a/spec.md", "docs/a/spec.md"))

    def test_double_star(self):
        self.assertTrue(P.overlaps("scripts/**", "scripts/delivery/join.py"))
        self.assertTrue(P.overlaps("a/**/c.py", "a/b/d/c.py"))
        self.assertFalse(P.overlaps("a/**/c.py", "a/b/d/e.py"))
        self.assertFalse(P.overlaps("apps/web/**", "scripts/x.py"))

    def test_directory_entries(self):
        self.assertTrue(P.overlaps("docs/work", "docs/work/x/REPORT.md"))
        self.assertTrue(P.overlaps("docs/work/", "docs/work/x.md"))
        self.assertFalse(P.overlaps("docs/work", "docs/workflow/x.md"))

    def test_comma_in_note(self):
        t = "```delivery\nowns: x.py (refresh_plan, resolve_playwright only), y/z.py\n```\n"
        self.assertEqual(P.delivery_block(t)["owns"], ["x.py (refresh_plan, resolve_playwright only)", "y/z.py"])

    def test_same_file_disjoint_ids_allowed(self):
        self.assertFalse(P.overlaps("docs/s.md (R13.72 only)", "docs/s.md (R5.48 only)"))
        self.assertTrue(P.overlaps("docs/s.md (R13.72 only)", "docs/s.md (R13.72 only)"))
        self.assertTrue(P.overlaps("docs/s.md (R13.72 only)", "docs/s.md"))
        self.assertTrue(P.overlaps("docs/s.md (R13.72)", "docs/s.md (R5.48)"))

    def test_message_names_both_notes(self):
        info = P.overlap_info("docs/s.md (R1.1 only)", "docs/s.md (see text)")
        self.assertIn("R1.1 only", info)
        self.assertIn("see text", info)

    def test_prose_ignored(self):
        self.assertFalse(P.overlaps("existing agent_ci tests (any)", "tests/a.py"))
        self.assertFalse(P.overlaps("everything", "tests/a.py"))


if __name__ == "__main__":
    unittest.main()
