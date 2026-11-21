"""DS235b: the React parts render every state (one fixture app per part), and the Rust models pass their own tests."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _ds235b import PARTS, NODE, have_playwright, fixtures, node

REACT = PARTS / "react-typescript"
NAMES = ["FleetRows", "RemoteUpdate", "RemoveDialog", "UpdateBanner", "UpdateHistory", "UpdatesCard"]


class Source(unittest.TestCase):
    def test_every_part_has_a_fixture_and_uses_tokens_only(self):
        for n in NAMES:
            self.assertTrue((REACT / f"{n}.tsx").exists(), n)
            self.assertTrue((REACT / "fixtures" / f"{n}.fixture.tsx").exists(), n)
        css = (REACT / "lifecycle-parts.css").read_text()
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", css))
        self.assertIn("var(--ds-color-text)", css)

    def test_words_come_from_the_table(self):
        for n in NAMES:
            src = (REACT / f"{n}.tsx").read_text()
            self.assertIn("t(", src, n)
        self.assertIn("Delete my data too", (REACT / "words.ts").read_text())
        self.assertIn("Automatic when idle", (REACT / "words.ts").read_text())

    def test_remove_dialog_disables_remove_until_chosen(self):
        src = (REACT / "RemoveDialog.tsx").read_text()
        self.assertIn("disabled={!choice}", src)


@unittest.skipUnless(NODE and have_playwright(), "node with playwright needed")
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fixtures()
        if not cls.fx:
            raise unittest.SkipTest("react and esbuild not available")

    def run_js(self, name, script):
        import json, os
        js = "const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:393,height:800}});" \
             f"await p.goto('file://{self.fx}/{name}.html');const r=await p.evaluate(()=>{{{script}}});console.log(JSON.stringify(r));await b.close()}})()"
        p = subprocess.run([NODE, "-e", js], capture_output=True, text=True, env=os.environ)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_banner_shows_all_four_states(self):
        r = self.run_js("UpdateBanner", "return [...document.querySelectorAll('[data-ds-part=update-banner]')].map(e=>e.dataset.state)")
        self.assertEqual(r, ["ready", "running", "done", "failed"])

    def test_remove_is_disabled_until_a_choice(self):
        r = self.run_js("RemoveDialog", "return [...document.querySelectorAll('[data-ds-part=remove-dialog] .ds-btn--primary')].map(b=>b.disabled)")
        self.assertEqual(r, [True, False, False])

    def test_remove_names_size_and_path(self):
        r = self.run_js("RemoveDialog", "return document.body.innerText")
        self.assertIn("1.4 GB", r)
        self.assertIn("Keep my data", r)
        self.assertIn("Delete my data too", r)

    def test_updates_card_policies_and_lock(self):
        r = self.run_js("UpdatesCard", "return {t: document.body.innerText, locked: [...document.querySelectorAll('fieldset')].map(f=>f.disabled)}")
        self.assertIn("Automatic when idle", r["t"])
        self.assertIn("Ask first", r["t"])
        self.assertIn("Set by an administrator", r["t"])
        self.assertEqual(r["locked"], [False, False, True])

    def test_fleet_rows_words(self):
        r = self.run_js("FleetRows", "return document.body.innerText")
        for w in ("Up to date", "Waiting", "Needs you"):
            self.assertIn(w, r)

    def test_touch_targets(self):
        r = self.run_js("RemoteUpdate", "return [...document.querySelectorAll('button')].every(b=>b.getBoundingClientRect().height>=44)")
        self.assertTrue(r)


@unittest.skipUnless(shutil.which("rustc"), "rustc needed")
class RustModels(unittest.TestCase):
    def test_models_pass_their_unit_tests(self):
        for f in ("question_window.rs", "tray_menu.rs"):
            out = Path(tempfile.mkdtemp()) / "t"
            p = subprocess.run(["rustc", "--edition", "2021", "--test", str(PARTS / "rust" / f), "-o", str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            q = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(q.returncode, 0, q.stdout)


if __name__ == "__main__":
    unittest.main()
