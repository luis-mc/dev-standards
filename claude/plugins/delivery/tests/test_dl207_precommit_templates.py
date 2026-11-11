"""DL207: the pre-commit secret pattern ignores CSS selectors and still catches assignments.

Also scans every shipped template in all plugins with the hook's own pattern.
"""
import re
import unittest
from pathlib import Path

import _helpers  # noqa: F401
from test_dl204_install_secret_scan import hook_patterns, offenders, REPO

PLUGINS = REPO / "claude" / "plugins"


def hits(line):
    pat, doc, ci = hook_patterns()
    return bool(pat.search(line) and not doc.search(line) and not ci.search(line))


class PatternTests(unittest.TestCase):
    def test_catches_assignments(self):
        for line in [
            "FOO_" + "KEY=abc",
            "FOO_" + "KEY: abc",
            "const FOO_" + "KEY = 'x'",
            'FOO_' + 'TOKEN:"x"',
            "DATABASE_" + "URL=x",
            "by_" + "key = {}",
            "MY_" + "SECRET = load()",
        ]:
            with self.subTest(line=line):
                self.assertTrue(hits(line))

    def test_ignores_selectors_and_empty_values(self):
        for line in [
            ".ds-keypad__" + "key:active {",
            ".a_" + "key::before {",
            "FOO_" + "KEY: {",
            "button.some_" + "key:hover { color: red; }",
        ]:
            with self.subTest(line=line):
                self.assertFalse(hits(line))


class TemplateScanTests(unittest.TestCase):
    def test_every_plugin_template_is_clean(self):
        dirs = sorted(PLUGINS.glob("*/templates"))
        self.assertTrue(dirs)
        self.assertIn(PLUGINS / "docs" / "templates", dirs)
        bad = []
        for d in dirs:
            bad += ["%s: %s" % (d.parent.name, b) for b in offenders(d)]
        self.assertEqual(bad, [])

    def test_keypad_css_is_scanned_and_clean(self):
        css = PLUGINS / "docs/templates/design-system/components/react-typescript/number-keypad.css"
        self.assertTrue(css.is_file())
        self.assertEqual(offenders(css.parent), [])


if __name__ == "__main__":
    unittest.main()
