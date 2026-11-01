import unittest
from _helpers import *  # noqa
import docs_lib as D


class LibTests(unittest.TestCase):
    def test_front_matter_parse(self):
        fm, body, ok = D.parse_front_matter('---\nid: a  # c\napps: [web, "home x"]\nflag: true\nq: "a # b"\nempty:\n---\nbody\n')
        self.assertTrue(ok)
        self.assertEqual(fm["id"], "a")
        self.assertEqual(fm["apps"], ["web", "home x"])
        self.assertIs(fm["flag"], True)
        self.assertEqual(fm["q"], "a # b")
        self.assertEqual(fm["empty"], "")
        self.assertEqual(body, "body\n")

    def test_front_matter_block_list(self):
        t = ('---\nid: a\ncode:\n  - claude/plugins/x/scripts/*.py  # c\n'
             '  - "tools/test_*.py"\n- plain\nnext: v\n---\nB\n')
        fm = D.parse_front_matter(t)[0]
        self.assertEqual(fm["code"], ["claude/plugins/x/scripts/*.py", "tools/test_*.py", "plain"])
        self.assertEqual(fm["next"], "v")

    def test_front_matter_flow_list_unchanged(self):
        fm = D.parse_front_matter("---\ncode: [a/*.py, b]\nz: 1\n---\n")[0]
        self.assertEqual(fm["code"], ["a/*.py", "b"])
        self.assertEqual(fm["z"], "1")

    def test_front_matter_empty_without_list(self):
        fm = D.parse_front_matter("---\ncode:\nz: 1\n---\n")[0]
        self.assertEqual(fm["code"], "")
        self.assertEqual(fm["z"], "1")

    def test_set_front_matter_keeps_block_list(self):
        t = "---\nversion: 1.0.0\ncode:\n  - a/*.py\n  - b.py\nlast_verified: 2026-01-01\n---\nB\n"
        out = D.set_front_matter(t, {"version": "1.1.0", "last_verified": "2026-02-02"})
        self.assertIn("code:\n  - a/*.py\n  - b.py\n", out)
        self.assertEqual(D.parse_front_matter(out)[0]["code"], ["a/*.py", "b.py"])
        self.assertIn("version: 1.1.0", out)

    def test_front_matter_absent_or_unclosed(self):
        self.assertFalse(D.parse_front_matter("# x\n")[2])
        self.assertFalse(D.parse_front_matter("---\nid: a\n")[2])

    def test_set_front_matter_keeps_comments_and_adds(self):
        t = "---\nid: a\nversion: 1.0.0   # fold\n---\nB\n"
        out = D.set_front_matter(t, {"version": "1.1.0", "owner": "x"})
        self.assertIn("version: 1.1.0   # fold", out)
        self.assertIn("owner: x", out)
        self.assertTrue(out.endswith("B\n"))
        self.assertTrue(D.set_front_matter("B\n", {"id": "z"}).startswith("---\nid: z\n---\nB"))

    def test_glob(self):
        self.assertTrue(D.glob_to_regex("apps/web/**").match("apps/web/src/a.ts"))
        self.assertTrue(D.glob_to_regex("a/**/b.py").match("a/b.py"))
        self.assertTrue(D.glob_to_regex("a/*.py").match("a/b.py"))
        self.assertFalse(D.glob_to_regex("a/*.py").match("a/x/b.py"))

    def test_anchors_and_slug(self):
        a = D.anchors("# One\n## Two words\n## Two words\n```\n# no\n```\n")
        self.assertEqual(a, {"one", "two-words", "two-words-1"})

    def test_links_in_code_are_ignored(self):
        t = D.strip_code("a `[x](y.md)` b\n```\n[q](z.md)\n```\n[ok](o.md)")
        self.assertEqual([m.group(1) for m in D.LINK_RE.finditer(t)], ["o.md"])

    def test_external(self):
        for t in ("https://x", "mailto:a@b", "#a", "//cdn"):
            self.assertTrue(D.is_external(t))
        self.assertFalse(D.is_external("a/b.md"))

    def test_config_defaults_and_override(self):
        d = make_repo({"docs/docs.json": '{"apps": ["web"], "stale_days": 10}'})
        c = D.load_config(d)
        self.assertEqual(c["apps"], ["web"])
        self.assertEqual(c["record_dir"], "docs/project")
        self.assertEqual(c["stale_days"], 10)

    def test_is_binding(self):
        c = D.DEFAULTS
        self.assertTrue(D.is_binding("docs/features/x/spec.md", c))
        self.assertFalse(D.is_binding("docs/architecture/decisions.md", c))
        self.assertFalse(D.is_binding("docs/guides/setup.md", c))


if __name__ == "__main__":
    unittest.main()
