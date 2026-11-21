"""DS235b: the DS234 guards (A-E) and the lifecycle guards LC-22/23/24/30. Each passes a clean input and fails a broken one."""
import os
import tempfile
import unittest
from pathlib import Path

from _ds235b import GUARDS, NODE, node, have_playwright, page, fixtures

DG = GUARDS / "design-guards"
LG = GUARDS / "lifecycle"
PW = unittest.skipUnless(NODE and have_playwright(), "node with playwright needed")


def tmp(files):
    d = Path(tempfile.mkdtemp(prefix="ds235b-"))
    for rel, text in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


CARDS = '<main style="padding:16px"><div style="display:flex;flex-direction:column;gap:var(--ds-space-6)">{}</div></main>'
FIELDS = ('<section data-ds-section><input id="a" class="f"></section>'
          '<section data-ds-section><input id="b" class="f"></section>')


@PW
class GuardA(unittest.TestCase):
    def run_a(self, f, *extra):
        return node(DG / "rendered-layout.mjs", f, "--widths", "360,1300", *extra)

    def test_clean_passes(self):
        rc, out = self.run_a(page(CARDS.format(FIELDS), ".f{display:block;box-shadow:none}.f:focus{outline:3px solid blue}"))
        self.assertEqual(rc, 0, out)

    def test_focus_glow_overlap_fails(self):
        # the section gap is 32 px; a 40 px focus glow reaches the next field
        rc, out = self.run_a(page(CARDS.format(FIELDS), ".f{display:block}.f:focus{box-shadow:0 0 0 40px rgba(0,0,255,.3)}"))
        self.assertEqual(rc, 1, out)
        self.assertIn("overlaps", out)
        self.assertIn("focused", out)

    def test_static_overlap_fails(self):
        body = '<div style="position:relative"><button id="x" style="position:absolute;top:0;left:0;width:100px;height:50px">a</button>' \
               '<button style="position:absolute;top:20px;left:50px;width:100px;height:50px">b</button></div>'
        rc, out = self.run_a(page(body))
        self.assertEqual(rc, 1, out)

    def test_section_gap_must_equal_token(self):
        body = '<main><section data-ds-section>a</section><section data-ds-section style="margin-top:7px">b</section></main>'
        rc, out = self.run_a(page(body))
        self.assertEqual(rc, 1, out)
        self.assertIn("section-gap", out)

    def test_section_gap_equal_passes(self):
        body = '<main style="display:flex;flex-direction:column;gap:var(--ds-space-6)"><section data-ds-section>a</section><section data-ds-section>b</section></main>'
        rc, out = self.run_a(page(body))
        self.assertEqual(rc, 0, out)


class GuardB(unittest.TestCase):
    def test_tokens_pass(self):
        d = tmp({"a.css": ".a{margin:0;padding:var(--ds-space-3) var(--ds-space-4);gap:calc(var(--ds-space-2) * 2)}"})
        self.assertEqual(node(DG / "spacing-tokens.mjs", d)[0], 0)

    def test_raw_px_fails(self):
        d = tmp({"a.css": ".a{padding:12px}", "b.tsx": "const s = {marginTop: 8}; const t = { gap: '1rem' };"})
        rc, out = node(DG / "spacing-tokens.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("a.css:1", out)
        self.assertIn("marginTop", out)
        self.assertIn("gap", out)

    def test_token_file_is_exempt(self):
        d = tmp({"tokens.css": ":root{--ds-space-4:16px}.x{padding:16px}"})
        self.assertEqual(node(DG / "spacing-tokens.mjs", d)[0], 0)


class GuardC(unittest.TestCase):
    CFG = '{"roles":{"page-sections":"PageSections","card-grid":"CardGrid","form":"FormStack"},"pages":["src/pages"]}'
    COMP = "## 37. PageSections\n## 38. CardGrid\n## 39. FormStack\n"

    def files(self, page_src, comp=None):
        return {"layout-roles.json": self.CFG, "docs/design-system/next-version/components.md": comp or self.COMP,
                "src/pages/Home.tsx": page_src}

    def test_clean_passes(self):
        d = tmp(self.files("<PageSections><section/><section/></PageSections>"))
        rc, out = node(DG / "layout-roles.mjs", d)
        self.assertEqual(rc, 0, out)

    def test_plain_gap_fails(self):
        d = tmp(self.files("<main style={{display:'flex', gap: 'var(--ds-space-6)'}}><section/><section/></main>"))
        rc, out = node(DG / "layout-roles.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("plain gap", out)

    def test_sections_without_component_fail(self):
        d = tmp(self.files("<main><section/><section/></main>"))
        self.assertEqual(node(DG / "layout-roles.mjs", d)[0], 1)

    def test_missing_component_in_design_system_fails(self):
        d = tmp(self.files("<PageSections><section/><section/></PageSections>", comp="## 1. Other\n"))
        rc, out = node(DG / "layout-roles.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("does not name PageSections", out)


class GuardD(unittest.TestCase):
    ROW = "| ID | Rule | Guard |\n|---|---|---|\n| UX-1 | x | {} |\n"

    def run_d(self, guard, days=None):
        files = {"ux-rules.md": self.ROW.format(guard)}
        if days:
            files["tools/design-guards.json"] = '{"none_yet_days": %d}' % days
        d = tmp(files)
        cwd = os.getcwd()
        os.chdir(d)
        try:
            return node(DG / "none-yet.mjs", d / "ux-rules.md", env={"DS_TODAY": "2026-11-21"})
        finally:
            os.chdir(cwd)

    def test_recent_date_passes(self):
        self.assertEqual(self.run_d("none yet (2026-11-01)")[0], 0)

    def test_expired_fails(self):
        rc, out = self.run_d("none yet (2026-09-01)")
        self.assertEqual(rc, 1)
        self.assertIn("81 days old", out)

    def test_no_date_fails(self):
        self.assertEqual(self.run_d("none yet")[0], 1)

    def test_limit_from_config(self):
        self.assertEqual(self.run_d("none yet (2026-11-01)", days=10)[0], 1)

    def test_real_guard_passes(self):
        self.assertEqual(self.run_d("`tests/x.test.ts`")[0], 0)


class GuardE(unittest.TestCase):
    def test_citation_with_test_passes(self):
        d = tmp({"tests/ux.test.ts": "", "docs/features/a/spec.md": "Follows UX-4, proof `tests/ux.test.ts`.\n"})
        rc, out = node(DG / "citation-test.mjs", d)
        self.assertEqual(rc, 0, out)

    def test_proof_line_passes(self):
        d = tmp({"tests/ux.test.ts": "", "docs/features/a/spec.md": "Follows CORE-1.\n\nProof: CORE-1 `tests/ux.test.ts`\n"})
        self.assertEqual(node(DG / "citation-test.mjs", d)[0], 0)

    def test_citation_without_test_fails(self):
        d = tmp({"docs/features/a/spec.md": "Follows UX-4.\n"})
        rc, out = node(DG / "citation-test.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("UX-4", out)

    def test_test_path_must_exist(self):
        d = tmp({"docs/features/a/spec.md": "Follows UX-4, proof `tests/missing.test.ts`.\n"})
        self.assertEqual(node(DG / "citation-test.mjs", d)[0], 1)


class LC22(unittest.TestCase):
    OK = "pub const NOTICE_WINDOW_SECS: u64 = 24 * 60 * 60;\npub fn notify() {}\n"

    def test_clean_tray_passes(self):
        d = tmp({"tray_menu.rs": self.OK})
        rc, out = node(LG / "tray-modal.mjs", d)
        self.assertEqual(rc, 0, out)

    def test_modal_tray_fails(self):
        d = tmp({"tray_menu.rs": self.OK + "fn ask() { MessageBox::new().yes_no(); }\n"})
        rc, out = node(LG / "tray-modal.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("LC-22", out)

    def test_no_24h_window_fails(self):
        d = tmp({"tray_menu.rs": "pub const NOTICE_WINDOW_SECS: u64 = 60;\n"})
        self.assertEqual(node(LG / "tray-modal.mjs", d)[0], 1)
        d = tmp({"tray_menu.rs": "fn f() {}\n"})
        self.assertEqual(node(LG / "tray-modal.mjs", d)[0], 1)

    def test_shipped_rust_templates_pass(self):
        rc, out = node(LG / "tray-modal.mjs", GUARDS.parent / "parts" / "rust")
        self.assertEqual(rc, 0, out)

    def test_fixed_size_window_fails(self):
        d = tmp({"question_window.rs": "fn open() { builder.with_inner_size(LogicalSize::new(480, 320)); }\n"})
        rc, out = node(LG / "tray-modal.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("LC-30", out)

    def test_sized_from_content_passes(self):
        d = tmp({"question_window.rs": "fn open(s: Size) { builder.with_inner_size(s); }\n"})
        self.assertEqual(node(LG / "tray-modal.mjs", d)[0], 0)


class LC23(unittest.TestCase):
    GOOD = '<div className="ds-part" data-ds-part="x"/>'

    def test_shipped_parts_pass(self):
        rc, out = node(LG / "parts-tokens.mjs", GUARDS.parent / "parts" / "react-typescript")
        self.assertEqual(rc, 0, out)

    def test_clean_passes(self):
        d = tmp({"A.tsx": self.GOOD, "lifecycle-parts.css": ".a{color:var(--ds-color-text);padding:var(--ds-space-3)}"})
        self.assertEqual(node(LG / "parts-tokens.mjs", d)[0], 0)

    def test_raw_colour_and_size_fail(self):
        d = tmp({"A.tsx": self.GOOD, "lifecycle-parts.css": ".a{color:#fff;padding:12px;font-family:Arial}"})
        rc, out = node(LG / "parts-tokens.mjs", d)
        self.assertEqual(rc, 1)
        for w in ("raw colour", "raw size", "font family"):
            self.assertIn(w, out)

    def test_part_off_the_shared_template_fails(self):
        d = tmp({"A.tsx": '<div style={{color:"red"}} data-ds-part="x"/>'})
        rc, out = node(LG / "parts-tokens.mjs", d)
        self.assertEqual(rc, 1)
        self.assertIn("ds-part", out)


@PW
class LC24(unittest.TestCase):
    def test_shipped_fixture_states_pass(self):
        fx = fixtures()
        if not fx:
            self.skipTest("react and esbuild not available")
        pages = sorted(fx.glob("*.html"))
        self.assertEqual(len(pages), 6)
        rc, out = node(LG / "states-render.mjs", *pages)
        self.assertEqual(rc, 0, out)

    def test_clipped_text_fails(self):
        body = '<div class="ds-part" style="width:100px;overflow:hidden"><p style="white-space:nowrap">A very long line that does not fit</p></div>'
        rc, out = node(LG / "states-render.mjs", page(body), "--scales", "1")
        self.assertEqual(rc, 1, out)
        self.assertIn("clipped", out)

    def test_overflow_at_360_fails(self):
        rc, out = node(LG / "states-render.mjs", page('<div style="width:500px;height:20px">x</div>'), "--scales", "1")
        self.assertEqual(rc, 1)
        self.assertIn("overflow", out)

    def test_overlap_at_scale_fails(self):
        body = '<button style="position:absolute;top:0;left:0">one</button><button style="position:absolute;top:10px;left:10px">two</button>'
        rc, out = node(LG / "states-render.mjs", page(body), "--scales", "2")
        self.assertEqual(rc, 1)
        self.assertIn("overlap", out)

    def test_fixed_height_window_clips_at_200(self):
        body = '<div class="ds-part" style="height:60px;overflow:hidden"><p>Remove</p><p>Choose what happens to your data</p><button class="ds-btn">Remove</button></div>'
        rc, out = node(LG / "states-render.mjs", page(body, ".ds-btn{min-height:44px}"), "--scales", "2")
        self.assertEqual(rc, 1, out)


if __name__ == "__main__":
    unittest.main()
