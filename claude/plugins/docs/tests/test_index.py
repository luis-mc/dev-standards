import json
import unittest
from _helpers import *  # noqa
import docs_index as I
import docs_lib as D

SPEC = spec(body="# Import\n\nSee [auth](../../architecture/sec.md) and ![shot](images/a.png)\n\n```mermaid\nflowchart LR\n a-->b\n```\n\n| a | b |\n|---|---|\n| 1 | **2** |\n\n- x\n- y\n")


def proj(extra=None):
    return project({**(extra or {}),
        "docs/features/import/spec.md": SPEC,
        "docs/features/import/images/a.png": "png",
        "docs/features/reader/spec.md": spec(fid="reader", apps="[web, home]", topics="[reading]", status="building", version="0.2.0", code="[]", body="# Reader\n"),
        "docs/architecture/sec.md": "# Sec\n",
        "docs/architecture/decisions/0001-db.md": "---\nid: 0001-db\ntitle: Use a database\nstatus: accepted\ndate: 2026-10-01\n---\n# Use a database\n",
        "docs/project/content/import/decisions.json": json.dumps({"decisions": [
            {"id": "D1", "question": "Layout?", "status": "decided", "chosen": "B", "decided": "2026-10-31"},
            {"id": "D2", "question": "Open one", "status": "open"}]}),
    }, apps=("web", "home", "admin"), topics=("library", "reading"))


class RenderTests(unittest.TestCase):
    def test_markdown_subset(self):
        h = I.render_markdown("# T\n\npara **b** `c<d>` [l](x.md)\n\n- a\n- b\n\n1. o\n\n> q\n\n```py\nx<1\n```\n")
        self.assertIn('<h1 id="t">T</h1>', h)
        self.assertIn("<strong>b</strong>", h)
        self.assertIn("<code>c&lt;d&gt;</code>", h)
        self.assertIn('<a href="x.md">l</a>', h)
        self.assertIn("<ul><li>a</li><li>b</li></ul>", h)
        self.assertIn("<ol><li>o</li></ol>", h)
        self.assertIn("<blockquote>", h)
        self.assertIn("x&lt;1", h)

    def test_table_and_mermaid(self):
        h = I.render_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n\n```mermaid\nflowchart LR\n```\n")
        self.assertIn("<th>a</th>", h)
        self.assertIn("<td>2</td>", h)
        self.assertIn('<pre class="mermaid">', h)

    def test_html_is_escaped(self):
        self.assertNotIn("<script>", I.render_markdown("a <script>alert(1)</script>"))


class BuildTests(unittest.TestCase):
    def test_build_writes_everything(self):
        d = proj()
        r_ = I.build(d)
        for rel in ("docs/index.html", "docs/llms.txt", "docs/features/index.md", "docs/architecture/decisions.md", "docs/docs-map.json",
                    "docs/_site/features/import/spec.html", "docs/_site/search-index.js", "docs/_site/features/import/images/a.png"):
            self.assertTrue((d / rel).is_file(), rel)
        self.assertEqual(r_["features"], 2)

    def test_feature_index_by_app_topic_status(self):
        d = proj()
        I.build(d)
        t = r(d, "docs/features/index.md")
        self.assertIn("### web", t)
        self.assertIn("### home", t)
        self.assertIn("### admin\n\nNo feature lists this app yet.", t)
        self.assertIn("### reading", t)
        self.assertIn("### building", t)
        # a feature used by two apps shows under both: web, home, topic reading, status building
        self.assertEqual(t.count("[T reader](reader/spec.md)"), 4)

    def test_gaps(self):
        d = proj()
        w(d, "docs/features/orphan/notes.md", "x")
        I.build(d)
        t = r(d, "docs/features/index.md")
        self.assertIn("orphan/: feature folder with no spec.md", t)
        self.assertIn("app admin: no feature spec lists it", t)
        self.assertIn("docs/features/reader/spec.md: no diagram or image", t)

    def test_decisions_index_lists_both_kinds(self):
        d = proj()
        I.build(d)
        t = r(d, "docs/architecture/decisions.md")
        self.assertIn("Use a database", t)
        self.assertIn("| import | D1 | Layout? | B | decided | 2026-10-31 |", t)
        self.assertNotIn("Open one", t)

    def test_docs_map(self):
        d = proj()
        I.build(d)
        m = json.loads(r(d, "docs/docs-map.json"))["map"]
        self.assertEqual(m, {"src/import/**": ["docs/features/import/spec.md"]})

    def test_decisions_from_spec_table(self):
        d = proj()
        w(d, "docs/features/reader/spec.md", spec(fid="reader", code="[]", body="# R\n\n## 10. Decisions\n\n| ID | Question | Chosen | Date |\n|---|---|---|---|\n| D4 | Shape? | One folder | 2026-10-30 |\n"))
        I.build(d)
        self.assertIn("| reader | D4 | [Shape?](../features/reader/spec.md) | One folder | decided | 2026-10-30 |", r(d, "docs/architecture/decisions.md"))

    def test_site_page_links_and_diagram_fallback(self):
        d = proj()
        old = I.PLUGIN_MERMAID
        I.PLUGIN_MERMAID = d / "no-such-copy.js"
        try:
            I.build(d)
        finally:
            I.PLUGIN_MERMAID = old
        h = r(d, "docs/_site/features/import/spec.html")
        self.assertIn('href="../../architecture/sec.html"', h)
        self.assertIn('src="images/a.png"', h)
        self.assertIn('class="mermaid"', h)
        self.assertIn("fetch-mermaid", h, "no vendored mermaid -> a note, source stays readable")
        self.assertIn("status: live", h)

    def test_committed_mermaid_is_the_default(self):
        self.assertTrue(I.PLUGIN_MERMAID.is_file(), "vendor/mermaid.min.js is committed")
        self.assertGreater(I.PLUGIN_MERMAID.stat().st_size, 1_000_000)
        self.assertIn(I.MERMAID_VERSION, (I.PLUGIN / "vendor/README.md").read_text())
        self.assertIn("MIT License", (I.PLUGIN / "vendor/LICENSE-mermaid").read_text())
        d = proj()
        I.build(d)  # no --mermaid, no env
        self.assertEqual((d / "docs/_site/vendor/mermaid.min.js").read_bytes(), I.PLUGIN_MERMAID.read_bytes())
        h = r(d, "docs/_site/features/import/spec.html")
        self.assertIn('src="../../vendor/mermaid.min.js"', h)
        self.assertNotIn("fetch-mermaid", h)

    def test_override_beats_committed_copy(self):
        d = proj()
        js = w(d, "mine.js", "window.mermaid={initialize(){}};")
        I.build(d, mermaid=str(js))
        self.assertEqual((d / "docs/_site/vendor/mermaid.min.js").read_text(), "window.mermaid={initialize(){}};")
        I.build(d)  # a fetched/earlier override in the site is kept
        self.assertEqual((d / "docs/_site/vendor/mermaid.min.js").read_text(), "window.mermaid={initialize(){}};")

    def test_mermaid_vendored(self):
        d = proj()
        js = w(d, "vendor/mermaid.min.js", "window.mermaid={initialize(){}};")
        I.build(d, mermaid=str(js))
        self.assertTrue((d / "docs/_site/vendor/mermaid.min.js").is_file())
        self.assertIn('src="../../vendor/mermaid.min.js"', r(d, "docs/_site/features/import/spec.html"))
        I.build(d)  # a rebuild keeps the vendored copy
        self.assertTrue((d / "docs/_site/vendor/mermaid.min.js").is_file())

    def test_home_page_works_from_file_url(self):
        d = proj()
        I.build(d)
        h = r(d, "docs/index.html")
        self.assertIn('id="q"', h)
        self.assertIn('src="_site/search-index.js"', h)
        self.assertNotIn("fetch(", h)
        self.assertIn("<h3>admin</h3>", h)
        self.assertIn("Gaps", h)
        idx = r(d, "docs/_site/search-index.js")
        self.assertTrue(idx.startswith("window.DOCS_SEARCH="))
        data = json.loads(idx[len("window.DOCS_SEARCH="):-1])
        self.assertTrue(any(x["k"] == "docs/features/import/spec.md" for x in data))

    def test_work_and_site_are_not_indexed(self):
        d = proj({"docs/work/reports/T.md": "# secret\n"})
        I.build(d)
        self.assertNotIn("secret", r(d, "docs/_site/search-index.js"))
        self.assertFalse((d / "docs/_site/work").exists())

    def test_check_detects_stale_generated(self):
        d = proj()
        I.build(d)
        self.assertEqual(I.stale_generated(d), [])
        w(d, "docs/features/import/spec.md", SPEC.replace("status: live", "status: building"))
        self.assertIn("docs/features/index.md", I.stale_generated(d))
        self.assertEqual(I.main(["check", "--root", str(d)]), 1)
        I.build(d)
        self.assertEqual(I.main(["check", "--root", str(d)]), 0)

    def test_build_is_deterministic(self):
        d = proj()
        I.build(d)
        a = {p: r(d, p) for p in ("docs/features/index.md", "docs/llms.txt", "docs/architecture/decisions.md", "docs/docs-map.json")}
        I.build(d)
        self.assertEqual(a, {p: r(d, p) for p in a})


if __name__ == "__main__":
    unittest.main()
