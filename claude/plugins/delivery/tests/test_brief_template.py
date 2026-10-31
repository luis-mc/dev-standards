"""The agent brief template keeps its shape: a parseable delivery block that carries the docs: line (DOCSPEC R8.5)."""
import re
import unittest
from pathlib import Path

import _helpers  # noqa: F401  (puts scripts/ on the path)
import hook_pre_tool as P

TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "agent-brief-template.md"
KEYS = ("task", "branch", "where", "model", "effort", "owns", "docs", "eta")


class BriefTemplateTests(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")
        self.block = P.delivery_block(self.text)

    def test_block_has_every_key_in_order(self):
        body = re.search(r"```delivery\s*\n(.*?)```", self.text, re.S).group(1)
        keys = [m.group(1) for m in re.finditer(r"^([a-z]+):", body, re.M)]
        self.assertEqual(keys, list(KEYS))

    def test_docs_line_is_read_by_the_hook_parser(self):
        self.assertIn("docs", self.block)
        self.assertIn("none", self.block["docs"])

    def test_docs_line_cites_docspec_and_the_none_form(self):
        self.assertIn("R8.5", self.text)
        self.assertIn("Docs: none", self.text)

    def test_other_keys_still_parse(self):
        self.assertEqual(self.block["where"], "cloud")
        self.assertEqual(self.block["effort"], "medium")


class TemplateEtaTests(unittest.TestCase):
    def test_example_block_parses_to_a_breakdown_when_filled(self):
        import hook_post_tool as H
        text = TEMPLATE.read_text(encoding="utf-8")
        filled = text.replace("<m>", "10").replace("<total>", "30")
        b = H.parse_delivery_block(filled)
        self.assertEqual(b["breakdown"], {"setup": 10.0, "work": 10.0, "checks": 10.0})
        self.assertEqual(b["total_min"], 30.0)


if __name__ == "__main__":
    unittest.main()
