"""DL331: the picker templates target strict TypeScript (exactOptionalPropertyTypes,
noUncheckedIndexedAccess) and typescript-eslint. Grep-level guards, no npm."""
import re
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "templates/design-system/components/react-typescript"
SOURCES = sorted(p for p in DIR.iterdir() if p.suffix in (".ts", ".tsx"))
ALLOWED_HOOKS_REASON = re.compile(r"dependency array|deps? (are|is) (not|intentionally)", re.I)
OPTIONAL = re.compile(r"^\s*(\w+)\?:\s*([^;]+);", re.M)


class PickerStrictTests(unittest.TestCase):
    def test_sources_found(self):
        self.assertGreaterEqual(len(SOURCES), 8)

    def test_no_bare_exhaustive_deps_disable(self):
        for p in SOURCES:
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if "eslint-disable" in line and "react-hooks/exhaustive-deps" in line:
                    self.assertRegex(line, ALLOWED_HOOKS_REASON, f"{p.name}:{n} stale disable without a reason")

    def test_optional_props_passed_undefined_accept_undefined(self):
        """An optional prop that a component copies into an options object (so it can be
        undefined) must be declared `?: T | undefined` under exactOptionalPropertyTypes."""
        logic = (DIR / "number-keypad-logic.ts").read_text()
        comp = (DIR / "NumberKeypad.tsx").read_text()
        m = re.search(r"const opts = \{([^}]*)\}", comp)
        self.assertIsNotNone(m)
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        body = re.search(r"interface KeypadOptions \{(.*?)\n\}", logic, re.S).group(1)
        for opt in OPTIONAL.finditer(body):
            has_default = re.search(rf"\b{opt.group(1)}\s*=\s*[^=]", comp.split('const opts')[0])
            if opt.group(1) in names and not has_default:
                self.assertIn("undefined", opt.group(2), f"KeypadOptions.{opt.group(1)} must allow undefined")

    def test_no_index_signature_dot_access_in_known_spots(self):
        logic = (DIR / "date-picker-logic.ts").read_text()
        self.assertNotRegex(logic, r"\bgot\.[ymd]\b")
        self.assertNotIn(".dataset.keypadKey", (DIR / "NumberKeypad.tsx").read_text())

    def test_no_non_null_assertion_on_descriptor(self):
        self.assertNotIn("')!.set!", (DIR / "test-dom.ts").read_text())


if __name__ == "__main__":
    unittest.main()
