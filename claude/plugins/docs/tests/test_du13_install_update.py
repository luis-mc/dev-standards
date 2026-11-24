"""DU13: install and update window rules, templates and the layout-check template."""
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
DS = PLUGIN / "templates" / "design-system"
TPL = DS / "components" / "windows-installer"
NV = DS / "next-version"
NEW = [TPL / n for n in ("make-installer-art.ts", "installer-art.wxs", "update-window.ps1", "README.md")]


def code_lines(path):
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip().startswith(("//", "#", "<!--", "*")):
            continue
        out.append(ln)
    return "\n".join(out)


class RuleTests(unittest.TestCase):
    def test_rules_exist_with_unique_ids(self):
        text = (NV / "ux-rules.md").read_text(encoding="utf-8")
        ids = re.findall(r"(?m)^\| (UX-\d+) \|", text)
        self.assertEqual(len(ids), len(set(ids)))
        for n in (62, 63, 64, 65):
            self.assertIn(f"UX-{n}", ids)
        self.assertEqual(max(int(i[3:]) for i in ids), 69)  # UX-66 to UX-68 added by DS235b, UX-69 by DU15

    def test_components_cite_the_rules(self):
        text = (NV / "components.md").read_text(encoding="utf-8")
        self.assertIn("## 35. Update window", text)
        self.assertIn("## 36. Installer artwork", text)
        for n in (62, 63, 64, 65):
            self.assertIn(f"UX-{n}", text)
        self.assertIn("C14", (NV / "CHANGES.md").read_text(encoding="utf-8"))

    def test_skill_mentions_default(self):
        s = (PLUGIN / "skills/design-system-setup/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("UX-62 to UX-65", s)


class BitmapTests(unittest.TestCase):
    def test_source_has_no_hex_literals(self):
        src = code_lines(TPL / "make-installer-art.ts")
        self.assertIn("readTokens", src)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", src))
        self.assertIsNone(re.search(r"0x[0-9a-fA-F]{6}\b", src))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_writes_two_bmps_with_token_colours(self):
        tokens = NV / "tokens.md"
        want = {tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
                for h in re.findall(r"#([0-9a-fA-F]{6})", tokens.read_text(encoding="utf-8"))}
        out = Path(tempfile.mkdtemp(prefix="du13-"))
        r = subprocess.run(["node", "--experimental-strip-types", str(TPL / "make-installer-art.ts"), str(tokens), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0 and "strip-types" in r.stderr:
            self.skipTest("node cannot run TypeScript")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, (w, h) in (("banner.bmp", (493, 58)), ("dialog.bmp", (493, 312))):
            b = (out / name).read_bytes()
            self.assertEqual(b[:2], b"BM")
            bw, bh = struct.unpack_from("<ii", b, 18)
            self.assertEqual((bw, bh), (w, h))
            self.assertEqual(struct.unpack_from("<H", b, 28)[0], 24)
            row = ((w * 3 + 3) // 4) * 4
            for y in range(h):
                for x in range(w):
                    o = 54 + y * row + x * 3
                    self.assertIn((b[o + 2], b[o + 1], b[o]), want)


class PowerShellTests(unittest.TestCase):
    def test_layout_check_switch(self):
        ps = (TPL / "update-window.ps1").read_text(encoding="utf-8")
        self.assertRegex(ps, r"\[switch\]\$LayoutCheck")
        for scale in ("1.0", "1.5", "2.0"):
            self.assertIn(scale, ps)
        self.assertIn("exit 1", ps)

    def test_no_fixed_height_on_content_controls(self):
        ps = code_lines(TPL / "update-window.ps1")
        self.assertIsNone(re.search(r"\.Height\s*=", ps))
        self.assertIsNone(re.search(r"-Height|ScrollBars|AutoScroll\s*=\s*\$true", ps))

    def test_no_message_box(self):
        for p in NEW:
            self.assertNotIn("MessageBox", code_lines(p), p.name)
        self.assertNotIn("MessageBox", code_lines(TPL / "update-window.ps1"))


class PrivacyTests(unittest.TestCase):
    def test_no_other_project_named(self):
        files = NEW + [NV / "ux-rules.md", NV / "components.md", NV / "CHANGES.md"]
        for p in files:
            t = p.read_text(encoding="utf-8").lower()
            for bad in ("/home/", "c:\\users", "@live.com", "c:\\users"):
                self.assertNotIn(bad, t, p.name)


if __name__ == "__main__":
    unittest.main()
