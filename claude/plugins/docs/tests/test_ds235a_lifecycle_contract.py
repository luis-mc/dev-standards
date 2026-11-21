"""DS235a: lifecycle schema (LC-1), words lint in four forms (LC-2, LC-31), setup step."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import *  # noqa  (puts scripts/ on sys.path)
import lifecycle_check as L

PLUGIN = Path(__file__).resolve().parent.parent
LC = PLUGIN / "templates" / "design-system" / "lifecycle"
GUARDS = PLUGIN / "templates" / "design-system" / "guards"
starter = json.loads((LC / "lifecycle.json").read_text())

BANNED_CASES = ["OK", "Yes", "No", "Install now", "Later", "daemon", "binary", "payload"]
PLAIN_CASES = {"error code": "Failed with 0x80070005", "HTTP status": "The server said HTTP 503", "doubled punctuation": "Done.."}


def tree(base: Path, lifecycle=True):
    d = base / "docs" / "design-system" / "next-version"
    d.mkdir(parents=True)
    if lifecycle:
        shutil.copyfile(LC / "lifecycle.json", d / "lifecycle.json")
    return d


class SchemaTests(unittest.TestCase):  # LC-1
    def test_starter_is_valid(self):
        self.assertEqual(L.validate(starter), [])

    def test_words_file_matches_the_starter_table(self):
        self.assertEqual(json.loads((LC / "words.json").read_text()), starter["words"])

    def broken(self, change):
        doc = copy.deepcopy(starter)
        change(doc)
        problems = L.validate(doc)
        self.assertTrue(problems)
        return " ".join(problems)

    def test_missing_targets(self):
        self.assertIn("targets", self.broken(lambda d: d.pop("targets")))

    def test_unknown_state(self):
        self.assertIn("is not one of", self.broken(lambda d: d["flows"]["update"]["states"].append("hibernating")))

    def test_transition_to_unknown_state(self):
        # a state of the contract that this flow did not list
        def f(d):
            d["flows"]["install"]["states"].remove("ready")
        self.assertIn("is not a state of this flow", self.broken(f))

    def test_no_keep_on_remove(self):
        self.assertIn("keep_on_remove", self.broken(lambda d: d.pop("keep_on_remove")))

    def test_banned_word_in_words(self):
        self.assertIn("banned word 'Later'", self.broken(lambda d: d["words"]["states"]["available"].update(secondary="Later")))

    def test_bad_target_os(self):
        self.assertIn("targets[0].os", self.broken(lambda d: d["targets"][0].update(os="beos")))


class WordsContentTests(unittest.TestCase):
    def test_table_holds_the_owner_words(self):
        s = starter["words"]["states"]
        self.assertEqual(s["menu"]["check"], "Look for updates")
        self.assertEqual(s["available"]["primary"], "Update to version {version}")
        self.assertEqual(s["available"]["secondary"], "Not now")
        self.assertEqual([s[k]["step"] for k in ("downloading", "verifying", "installing", "testing")],
                         ["Downloading", "Checking the download", "Installing", "Testing"])
        self.assertEqual(s["remove"]["keep"], "Keep my data")
        self.assertIn("Delete my data too", s["remove"]["purge"])

    def test_defaults_match_the_contract(self):
        d = starter["defaults"]
        self.assertEqual((d["check_hours"], d["check_jitter_pct"], d["self_test_limit_s"], d["telemetry"]), (6, 20, 180, "off"))
        self.assertEqual(d["retry_hours"], [1, 4])
        self.assertEqual(d["check_backoff_minutes"], [1, 5, 30, 120])


class PythonScannerTests(unittest.TestCase):  # language-free form
    def setUp(self):
        sys.path.insert(0, str(GUARDS / "words-lint-python"))
        import words_lint
        self.W = words_lint

    def test_clean_wxl_passes(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        f = base / "a.wxl"
        f.write_text('<WixLocalization><String Id="a">Look for updates</String><String Id="b">Version {version} is ready.</String></WixLocalization>')
        self.assertEqual(self.W.run(base, [f]), 0)

    def test_clean_plain_file_passes(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        f = base / "a.strings"
        f.write_text('# lifecycle\nkeep = Keep my data\ncancel = Cancel\n')
        self.assertEqual(self.W.run(base, [f]), 0)

    def test_each_banned_word_is_flagged(self):
        doc = starter
        for w in BANNED_CASES:
            found = self.W.check_strings([f"Press {w} to go"], doc)
            self.assertIn(f"banned word '{w}'", " ".join(x[2] for x in found), w)

    def test_plain_notices(self):
        for why, text in PLAIN_CASES.items():
            self.assertIn(why, self.W.plain_hits(text))
        self.assertEqual(self.W.plain_hits("Nothing changed. 500 MB free."), [])

    def test_bad_wxl_fails_and_missing_lifecycle_is_a_setup_error(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        f = base / "a.wxl"
        f.write_text('<WixLocalization><String Id="a">Click OK (error 5)</String></WixLocalization>')
        self.assertEqual(self.W.run(base, [f]), 1)
        self.assertEqual(self.W.run(Path(tempfile.mkdtemp()), [f]), 2)


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("node"), "node missing")
class TypeScriptFormTests(unittest.TestCase):
    def test_self_tests_pass_under_node(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        g = base / "scripts" / "design"
        g.mkdir(parents=True)
        for f in (GUARDS / "words-lint-typescript-vitest").iterdir():
            shutil.copyfile(f, g / f.name)
        shim = base / "node_modules" / "vitest"
        shim.mkdir(parents=True)
        (shim / "index.js").write_text(
            "import { describe, it } from 'node:test'; import assert from 'node:assert';\n"
            "export { describe, it };\n"
            "export const expect = (a) => ({ toEqual: (b) => assert.deepStrictEqual(a, b), "
            "toContain: (b) => assert.ok(a.includes(b), `${JSON.stringify(a)} lacks ${b}`) });\n")
        (base / "package.json").write_text('{"type":"module"}')
        r = run(["node", "--experimental-strip-types", "--test", "scripts/design/words-lint.test.ts"], base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@unittest.skipUnless(shutil.which("go"), "go missing")
class GoFormTests(unittest.TestCase):
    def test_self_tests_pass(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        g = base / "internal" / "wordslint"
        g.mkdir(parents=True)
        for f in (GUARDS / "words-lint-go").iterdir():
            shutil.copyfile(f, g / f.name)
        (base / "go.mod").write_text("module x\n\ngo 1.22\n")
        r = run(["go", "test", "./..."], base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@unittest.skipUnless(shutil.which("cargo"), "cargo missing")
class RustFormTests(unittest.TestCase):
    def test_self_tests_pass(self):
        base = Path(tempfile.mkdtemp())
        tree(base)
        (base / "src").mkdir()
        (base / "src" / "lib.rs").write_text("")
        (base / "tests").mkdir()
        shutil.copyfile(GUARDS / "words-lint-rust" / "words_lint.rs", base / "tests" / "words_lint.rs")
        (base / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n')
        r = run(["cargo", "test", "--offline", "--test", "words_lint"], base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class SetupTests(unittest.TestCase):
    def test_writes_only_for_a_local_app(self):
        base = Path(tempfile.mkdtemp())
        tree(base, lifecycle=False)
        f = base / "docs/design-system/next-version/lifecycle.json"
        self.assertTrue(L.setup(base, False, True).startswith("skipped"))
        self.assertFalse(f.exists())
        self.assertTrue(L.setup(base, True, False).startswith("would write"))
        self.assertFalse(f.exists())
        self.assertTrue(L.setup(base, True, True).startswith("wrote"))
        self.assertEqual(L.validate(json.loads(f.read_text())), [])

    def test_never_overwrites(self):
        base = Path(tempfile.mkdtemp())
        d = tree(base)
        (d / "lifecycle.json").write_text("{}")
        L.setup(base, True, True)
        self.assertEqual((d / "lifecycle.json").read_text(), "{}")

    def test_promotion_copies_the_file(self):
        import design_system as D
        src = Path(tempfile.mkdtemp())
        d = tree(src)
        dest = src / "v1"
        shutil.copytree(d, dest, ignore=shutil.ignore_patterns(*D.ONE_TIME))
        self.assertTrue((dest / "lifecycle.json").is_file())

    def test_init_does_not_copy_the_starter_into_the_layout(self):
        import design_system as D
        base = Path(tempfile.mkdtemp())
        D.cmd_init(base, True)
        self.assertFalse((base / "docs/design-system/lifecycle").exists())

    def test_cli_validates_the_starter(self):
        self.assertEqual(L.main(["validate", str(LC / "lifecycle.json")]), 0)


if __name__ == "__main__":
    unittest.main()
