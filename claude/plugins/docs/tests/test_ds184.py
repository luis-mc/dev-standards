"""DS184: regression tests for the docs plugin review findings F1 to F13."""
import argparse
import datetime
import json
import subprocess
import unittest
from unittest import mock

from _helpers import *  # noqa
import design_system as DS
import docs_check as C
import docs_fold as F
import docs_lib as D
import docs_setup as S

GOOD = spec(body="# T\n")


def proj(extra=None):
    files = {"docs/features/import/spec.md": GOOD}
    files.update(extra or {})
    d = project(files)
    I = __import__("docs_index")
    I.build(d)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "docs")
    return d


class Ds184Tests(unittest.TestCase):
    def test_f1_new_folder_files_listed_one_by_one(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/newdir/b.py", "y\n")
        self.assertIn("src/import/newdir/b.py", D.changed_files(d, "main"))

    def test_f12_non_ascii_names_not_escaped(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/é.py", "y\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "c")
        w(d, "src/import/è.py", "y\n")
        ch = D.changed_files(d, "main")
        self.assertIn("src/import/é.py", ch)
        self.assertIn("src/import/è.py", ch)

    def test_f2_other_docs_note_does_not_satisfy(self):
        d = proj({"docs/architecture/sec.md": "---\nid: sec\ntitle: Sec\nversion: 0.1.0\ncode: [src/sec/**]\n---\n# Top\n",
                  "docs/architecture/dm.md": "---\nid: dm\ntitle: Dm\nversion: 0.1.0\ncode: [src/dm/**]\n---\n# Top\n",
                  "src/sec/a.py": "x"})
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/sec/a.py", "y")
        w(d, "docs/architecture/changes/dm/T1.md", "---\nchange: patch\n---\nx\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "c")
        res = C.check_map(d, D.load_config(d), "main")
        self.assertEqual([x["path"] for x in res if x["code"] == "M1"], ["docs/architecture/sec.md"])

    def test_f3_init_records_real_default_branch(self):
        d = make_repo({"README.md": "# r\n"}, commit=True)
        git(d, "branch", "-m", "master")
        S.main(["init", "--root", str(d), "--apply"])
        self.assertEqual(json.loads(r(d, "docs/docs.json"))["default_branch"], "master")

    def test_f3_check_says_when_no_base(self):
        d = proj()
        git(d, "branch", "-m", "trunk")
        res = C.run_checks(d, None, reference=False)
        self.assertTrue(any(x["code"] == "M1" and x["severity"] == "warning" and "base" in x["message"] for x in res), res)

    def test_f4_bom_is_ignored(self):
        d = make_repo({"a.md": "﻿---\nid: a\n---\nbody\n"})
        fm, body, ok = D.parse_front_matter(D.read(d / "a.md"))
        self.assertTrue(ok)
        self.assertEqual(fm["id"], "a")

    def test_f5_git_output_is_utf8(self):
        seen = {}
        real = subprocess.run

        def fake(*a, **kw):
            seen.update(kw)
            return real(*a, **kw)
        d = make_repo({"a": "1"})
        with mock.patch.object(subprocess, "run", fake):
            D.git(d, "status")
        self.assertEqual(seen.get("encoding"), "utf-8")
        self.assertEqual(seen.get("errors"), "replace")

    def test_f7_underscore_kept_in_slug(self):
        self.assertEqual(D.heading_slug("The record_dir key"), "the-record_dir-key")
        self.assertIn("the-record_dir-key", D.anchors("## The record_dir key\n"))

    def test_f8_percent_encoded_links(self):
        d = proj({"docs/guides/my guide.md": "# G\n\n## Été\n", "docs/overview/glossary.md":
                  "# G\n\n[g](../guides/my%20guide.md) [h](../guides/my%20guide.md#%C3%A9t%C3%A9)\n"})
        res = C.check_links(d)
        self.assertEqual([x for x in res if x["code"] == "K1"], [])

    def test_f9_title_with_hash_round_trips(self):
        d = make_repo({"docs/specs/import.md": "# Import #2 rework\n**Version:** 1.0.0\n"})
        stub = S.front_matter_stubs
        text = D.set_front_matter("# Import #2 rework\n", {"title": "Import #2 rework"})
        self.assertEqual(D.parse_front_matter(text)[0]["title"], "Import #2 rework")
        for t in ("a: b", "[x] y", '"q" z', "it's # no"):
            text = D.set_front_matter("body\n", {"title": t})
            self.assertEqual(D.parse_front_matter(text)[0]["title"], t, t)

    def test_f10_inline_code_links_not_rewritten(self):
        d = make_repo({"docs/specs/import.md": "# I\nSee [n](../notes/howto.md) and `[x](../notes/howto.md)`.\n",
                       "docs/guides/howto.md": "# H\n"})
        S.rewrite_links(d, [{"old": "docs/notes/howto.md", "new": "docs/guides/howto.md"}])
        t = r(d, "docs/specs/import.md")
        self.assertIn("`[x](../notes/howto.md)`", t)
        self.assertIn("[n](../guides/howto.md)", t)

    def test_f11_aligned_separator(self):
        t = "# D\n\n## Versions\n\n| Version | Date | Release | Change | Task |\n|:---|:---|:---|:---|:---|\n| 1.0.0 | d | R | c | T |\n"
        out = F.add_row(t, "| 1.1.0 | d | R2 | c | T2 |")
        self.assertEqual(out.count("| Version |"), 1)
        self.assertLess(out.index("1.1.0"), out.index("1.0.0"))

    def test_f13_impossible_date_refused(self):
        d = project()
        self.assertEqual(DS.cmd_init(d, True), 0)
        a = argparse.Namespace(approved_by="owner", approved_on="2026-02-31", evidence="chat", apply=False)
        self.assertEqual(DS.cmd_promote(d, a), 2)
        a = argparse.Namespace(approved_by="owner", approved_on="2026-99-99", evidence="chat", apply=False, version="v1")
        self.assertEqual(DS.cmd_approve_impl(d, a), 2)

    def test_hooks_keep_exit_code(self):
        h = json.loads((D.Path(__file__).resolve().parent.parent / "hooks/hooks.json").read_text())
        for ev in h["hooks"].values():
            c = ev[0]["hooks"][0]["command"]
            self.assertIn("command -v python3", c)
            self.assertNotIn("||", c)


if __name__ == "__main__":
    unittest.main()
