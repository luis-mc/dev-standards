"""DL371 / DL-96: release assets carry the version; CI artifact names stay stable."""
import json
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
TPL = PLUGIN / "templates"
REF = PLUGIN / "references" / "release-asset-names.md"
SCHEMA = PLUGIN / "references" / "config-schema.json"
PACKAGES = sorted(TPL.glob("*/.github/workflows/package*.yml"))
NEW_FILES = [REF, Path(__file__)]
OTHER_PROJECTS = re.compile(r"\b(" + "|".join(["cap" + "tain", "ma" + "ple"]) + r")\b", re.I)


class Templates(unittest.TestCase):
    def test_packages_found(self):
        self.assertTrue(PACKAGES)

    def test_release_assets_versioned_and_opt_out(self):
        found = 0
        for p in PACKAGES:
            t = p.read_text()
            if "Name the release assets" not in t:
                continue
            found += 1
            self.assertIn("${PRODUCT}-${version}-win-${ARCH}.msi", t, p)
            self.assertIn("versioned_names", t, p)
            self.assertIn("SHA256SUMS", t, p)
        self.assertGreaterEqual(found, 1)

    def test_sha256sums_uses_versioned_names(self):
        t = (TPL / "shared/.github/workflows/package-windows.yml").read_text()
        i = t.index("Name the release assets")
        self.assertLess(t.index("cp \"$f\" \"release/$name\"", i), t.index("sha256sum", i))
        self.assertIn("cd release && sha256sum *", t)

    def test_artifact_names_stable(self):
        for p in PACKAGES + sorted(TPL.glob("*/.github/workflows/*.yml")):
            t = p.read_text()
            for m in re.finditer(r"upload-artifact@[^\n]*\n(?:[^\n]*\n){0,6}?\s*name:\s*([^\n]+)", t):
                self.assertNotIn("${{", m.group(1), "%s: %s" % (p, m.group(1)))
                self.assertNotRegex(m.group(1), r"\d+\.\d+", p)


class Docs(unittest.TestCase):
    def test_reference_covers(self):
        t = REF.read_text().lower()
        for k in ["fallback", "one release before", "<product>-<version>-<os>-<arch>", "release page", "stable names", "dl-22", "versioned_names"]:
            self.assertIn(k, t)

    def test_schema_key(self):
        d = json.loads(SCHEMA.read_text())
        v = d["properties"]["release_assets"]["properties"]["versioned_names"]
        self.assertEqual(v["type"], "boolean")
        self.assertIs(v["default"], True)
        self.assertTrue(v["description"])

    def test_no_other_project_named(self):
        for f in NEW_FILES:
            self.assertIsNone(OTHER_PROJECTS.search(f.read_text()), f)


if __name__ == "__main__":
    unittest.main()
