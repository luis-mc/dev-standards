"""DL385 / DL-96 / LC-32: one name <Product>-<version>-<os>-<arch>.<ext> for every release asset."""
import importlib.util
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
DELIVERY = PLUGIN / "templates" / "shared" / "scripts" / "delivery"
spec = importlib.util.spec_from_file_location("lifecycle_release_check", DELIVERY / "lifecycle_release_check.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

T = {
    "ExampleApp-2.5.0-win-x64.msi": {"os": "windows", "arch": "x64", "package": "msi"},
    "ExampleApp-2.5.0-linux-x64.deb": {"os": "linux", "arch": "x64", "package": "deb"},
    "ExampleApp-2.5.0-linux-arm64.rpm": {"os": "linux", "arch": "arm64", "package": "rpm"},
    "ExampleApp-2.5.0-macos-arm64.pkg": {"os": "macos", "arch": "arm64", "package": "pkg"},
}


def problems(name, target):
    return R.check_names("ExampleApp", [target], [name])


class Names(unittest.TestCase):
    def test_four_examples_pass(self):
        for name, t in T.items():
            self.assertEqual(problems(name, t), [], name)

    def test_all_four_together(self):
        self.assertEqual(R.check_names("ExampleApp", list(T.values()), list(T)), [])

    def test_prerelease_and_tar_gz(self):
        t = {"os": "linux", "arch": "x64", "package": "tar"}
        self.assertEqual(problems("ExampleApp-2.5.0-rc.1-linux-x64.tar.gz", t), [])

    def test_bad_names_fail(self):
        win = T["ExampleApp-2.5.0-win-x64.msi"]
        bad = ["ExampleApp-2.5.0-x64.msi",            # no os
               "ExampleApp-2.5.0-windows-x64.msi",    # wrong os word
               "ExampleApp-v2.5.0-win-x64.msi",       # leading v
               "Example App-2.5.0-win-x64.msi",       # space in product
               "ExampleApp-2.5.0-win-amd64.msi",      # wrong arch
               "ExampleApp-2.5.0-win-x64.exe.msi",    # odd ext
               "ExampleApp_2.5.0.msi"]                # old rule
        for n in bad:
            self.assertTrue(problems(n, win), n)

    def test_unknown_ext_fails(self):
        win = T["ExampleApp-2.5.0-win-x64.msi"]
        self.assertTrue(problems("ExampleApp-2.5.0-win-x64.rar", win))

    def test_os_must_match_target(self):
        self.assertTrue(problems("ExampleApp-2.5.0-linux-x64.msi", T["ExampleApp-2.5.0-win-x64.msi"]))

    def test_target_without_artifact_fails(self):
        out = R.check_names("ExampleApp", list(T.values()), [n for n in T if "macos" not in n])
        self.assertEqual(len(out), 1)
        self.assertIn("macos", out[0])

    def test_product_with_space_fails(self):
        self.assertTrue(R.check_names("Example App", [T["ExampleApp-2.5.0-win-x64.msi"]], ["Example App-2.5.0-win-x64.msi"]))


class Templates(unittest.TestCase):
    def test_windows_template_output_matches_rule(self):
        t = (PLUGIN / "templates/shared/.github/workflows/package-windows.yml").read_text()
        self.assertIn('"${PRODUCT}-${version}-win-${ARCH}.msi"', t)
        self.assertNotIn("INSTALLER_NAME", t)
        name = "ExampleApp-%s-win-%s.msi" % ("2.5.0", "x64")
        self.assertEqual(R.check_names("ExampleApp", [T[name]], [name]), [])

    def test_no_template_uses_old_rule(self):
        for p in (PLUGIN / "templates").rglob("*"):
            if p.is_file() and p.suffix in {".yml", ".sh", ".py"}:
                self.assertNotRegex(p.read_text(), r"<installer_name>_<version>", p)

    def test_reference_states_rule(self):
        t = (PLUGIN / "references/release-asset-names.md").read_text()
        self.assertIn("<Product>-<version>-<os>-<arch>.<ext>", t)
        self.assertIn("ExampleApp-2.5.0-macos-arm64.pkg", t)


if __name__ == "__main__":
    unittest.main()
