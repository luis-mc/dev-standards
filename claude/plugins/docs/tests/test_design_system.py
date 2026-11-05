import argparse
import json
import os
import re
import stat
import unittest

from _helpers import *  # noqa
import design_system as S
import gallery_draw as GD
import gallery_tokens as GT
import docs_check as C


def ds_repo():
    d = project()
    assert S.cmd_init(d, True) == 0
    return d


def args(**kw):
    a = argparse.Namespace(approved_by="owner", approved_on="2026-11-02", evidence="chat", apply=True)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def codes(res):
    return sorted({x["code"] for x in res})


def unlock(p):
    p.chmod(p.stat().st_mode | stat.S_IWUSR)


class DesignSystemTests(unittest.TestCase):
    def test_init_creates_layout_and_gallery(self):  # R15.1 R15.2
        d = ds_repo()
        for rel in ("README.md", "approvals.json", "next-version/README.md", "next-version/ux-rules.md", "next-version/components.md",
                    "next-version/tokens.md", "next-version/content.md", "next-version/CHANGES.md", "next-version/review-visuals/index.html"):
            self.assertTrue((d / "docs/design-system" / rel).is_file(), rel)
        self.assertEqual(S.check(d), [])
        self.assertEqual(S.enforced(d), "next-version")
        html = r(d, "docs/design-system/next-version/review-visuals/index.html")
        self.assertIn("UX-1", html)
        self.assertIn('class="sw"', html)  # colour swatches
        self.assertNotIn("src=\"http", html)
        self.assertNotIn("href=\"http", html)

    def test_init_never_overwrites(self):
        d = ds_repo()
        w(d, "docs/design-system/README.md", "# mine\n## Order of work\n")
        S.cmd_init(d, True)
        self.assertEqual(r(d, "docs/design-system/README.md"), "# mine\n## Order of work\n")

    def test_dry_run_changes_nothing(self):
        d = project()
        S.cmd_init(d, False)
        self.assertFalse((d / "docs/design-system/README.md").exists())

    def test_promote_needs_recorded_approval(self):  # R15.4
        d = ds_repo()
        self.assertEqual(S.cmd_promote(d, args(approved_by="")), 2)
        self.assertEqual(S.cmd_promote(d, args(evidence="")), 2)
        self.assertEqual(S.cmd_promote(d, args(approved_on="tomorrow")), 2)
        self.assertEqual(S.numbers(d), [])

    def test_promote_dry_run(self):
        d = ds_repo()
        self.assertEqual(S.cmd_promote(d, args(apply=False)), 0)
        self.assertEqual(S.numbers(d), [])

    def test_promote_needs_a_change_entry(self):
        d = ds_repo()
        w(d, "docs/design-system/next-version/CHANGES.md", "# c\n")
        self.assertEqual(S.cmd_promote(d, args()), 2)

    def test_promote_full_cycle(self):  # R15.3 R15.4 R15.5
        d = ds_repo()
        self.assertEqual(S.cmd_promote(d, args()), 0)
        ds = d / "docs/design-system"
        self.assertEqual(S.numbers(d), [1])
        self.assertEqual(S.enforced(d), "v1")
        self.assertIn("Approved by owner on 2026-11-02: chat", r(d, "docs/design-system/v1/README.md"))
        rec = json.loads(r(d, "docs/design-system/approvals.json"))["versions"]["v1"]
        self.assertEqual(rec["approved"]["date"], "2026-11-02")
        self.assertIsNone(rec["implementation"])
        self.assertEqual(rec["digest"], S.tree_digest(ds / "v1"))
        # next-version recreated as a writable copy with a draft status and an empty change list
        self.assertIn("draft", r(d, "docs/design-system/next-version/README.md"))
        self.assertNotIn("- C1", r(d, "docs/design-system/next-version/CHANGES.md"))
        self.assertEqual(r(d, "docs/design-system/next-version/tokens.md"), r(d, "docs/design-system/v1/tokens.md"))
        self.assertTrue(os.access(ds / "next-version/tokens.md", os.W_OK))
        self.assertFalse((ds / "v1/tokens.md").stat().st_mode & stat.S_IWUSR)
        self.assertEqual(S.check(d), [])
        # a second promotion needs a new change entry, then makes v2; v1 stays read-only
        self.assertEqual(S.cmd_promote(d, args()), 2)
        w(d, "docs/design-system/next-version/CHANGES.md", "# c\n\n- C1: new colour (tokens.md; owner)\n")
        self.assertEqual(S.cmd_promote(d, args(approved_on="2026-11-09")), 0)
        self.assertEqual(S.numbers(d), [1, 2])
        self.assertFalse((ds / "v1/tokens.md").stat().st_mode & stat.S_IWUSR)
        self.assertEqual(S.check(d), [])

    def test_approve_implementation(self):
        d = ds_repo()
        self.assertEqual(S.cmd_approve_impl(d, args(version="v1")), 2)  # nothing approved yet
        S.cmd_promote(d, args())
        self.assertEqual(S.cmd_approve_impl(d, args(version="v1", approved_on="2026-11-05")), 0)
        rec = json.loads(r(d, "docs/design-system/approvals.json"))["versions"]["v1"]
        self.assertEqual(rec["implementation"]["date"], "2026-11-05")
        self.assertEqual(S.check(d), [])  # approvals.json is not part of any digest

    def test_check_warns_on_edit_of_numbered_version(self):  # R15.5 R15.7
        d = ds_repo()
        S.cmd_promote(d, args())
        p = d / "docs/design-system/v1/tokens.md"
        unlock(p)
        p.write_text(p.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        res = S.check(d)
        self.assertIn("DS2", codes(res))
        self.assertEqual({x["severity"] for x in res}, {"warning"})

    def test_one_time_audit_does_not_break_digest(self):
        d = ds_repo()
        S.cmd_promote(d, args())
        w(d, "docs/design-system/v1/audit/index.html", "<p>audit</p>")
        self.assertEqual(S.check(d), [])

    def test_check_warns_on_branch_edit_of_numbered_version(self):  # R15.5
        d = ds_repo()
        S.cmd_promote(d, args())
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "ds")
        git(d, "checkout", "-q", "-b", "feat")
        p = d / "docs/design-system/v1/tokens.md"
        unlock(p)
        p.write_text("# edited\n", encoding="utf-8")
        git(d, "commit", "-qam", "edit v1")
        res = S.check(d, "main")
        self.assertTrue(any(x["path"].endswith("v1/tokens.md") and x["message"].startswith("M:") for x in res))

    def _archived_repo(self, where="docs/archive/design-system-v1"):
        d = ds_repo()
        S.cmd_promote(d, args())
        w(d, "docs/design-system/next-version/CHANGES.md", "# c\n\n- C1: new colour (tokens.md; owner)\n")
        S.cmd_promote(d, args(approved_on="2026-11-09"))
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "ds")
        git(d, "checkout", "-q", "-b", "feat")
        (d / where).parent.mkdir(parents=True, exist_ok=True)
        v1 = d / "docs/design-system/v1"
        for f in v1.rglob("*"):
            unlock(f)
        unlock(v1)
        os.rename(v1, d / where)
        return d

    def test_archived_version_is_not_a_gap(self):  # R15.1 R2.7
        for where in ("docs/archive/design-system-v1", "docs/archive/design-system/v1"):
            d = self._archived_repo(where)
            self.assertEqual([x for x in S.check(d) if "gap" in x["message"]], [], where)
            self.assertEqual(S.enforced(d), "v2")

    def test_gap_without_archive_still_warns(self):  # R15.1
        d = self._archived_repo()
        os.rename(d / "docs/archive/design-system-v1", d / "docs/archive/other")
        self.assertTrue(any("gap" in x["message"] for x in S.check(d)))

    def test_approval_of_archived_version_is_no_error(self):  # R15.4
        d = self._archived_repo()
        self.assertIn("v1", S.read_approvals(d)["versions"])
        self.assertEqual(S.check(d), [])

    def test_branch_archiving_a_version_is_not_an_edit(self):  # R15.5 R2.7
        d = self._archived_repo()
        git(d, "add", "-A")
        git(d, "commit", "-qm", "archive v1")
        self.assertEqual([x for x in S.check(d, "main") if x["code"] == "DS2"], [])

    def test_check_readme_order_of_work_and_layout(self):  # R15.2 R15.7
        d = ds_repo()
        w(d, "docs/design-system/README.md", "# DS\n")
        w(d, "docs/design-system/stray.md", "x\n")
        (d / "docs/design-system/next-version/tokens.md").unlink()
        self.assertEqual(codes(S.check(d)), ["DS1", "DS3", "DS4"])
        w(d, "docs/design-system/next-version/ux-rules.md", "# r\n| UX-1 | a | none yet |\n| UX-1 | b | none yet |\n")
        self.assertIn("DS5", codes(S.check(d)))

    def test_silent_without_design_system(self):
        self.assertEqual(S.check(project()), [])
        d = project()
        w(d, "docs/design-system/.gitkeep", "")
        self.assertEqual(S.check(d), [])

    def test_stale_gallery_warns_and_visuals_command_fixes(self):  # R15.2
        d = ds_repo()
        w(d, "docs/design-system/next-version/tokens.md", r(d, "docs/design-system/next-version/tokens.md") + "\n| `--ds-x` | `#123456` | x |\n")
        self.assertEqual(codes(S.check(d)), ["DS4"])
        self.assertEqual(S.main(["visuals", "--root", str(d)]), 0)
        self.assertEqual(S.check(d), [])
        S.cmd_promote(d, args())
        self.assertEqual(S.main(["visuals", "v1", "--root", str(d)]), 2)  # a numbered version is read-only

    def test_docs_check_includes_design_system(self):  # R8.1 R15.7
        d = ds_repo()
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "base")
        w(d, "docs/design-system/README.md", "# DS\n")
        res = C.run_checks(d, None, reference=False)
        self.assertIn("DS1", codes(res))
        self.assertEqual([x for x in res if x["severity"] == "error" and x["code"].startswith("DS")], [])

    def test_guard_templates_are_copied(self):  # R15.6
        d = project()
        self.assertEqual(S.main(["guards", "--root", str(d)]), 0)  # dry run
        self.assertFalse((d / "scripts/design").exists())
        self.assertEqual(S.main(["guards", "--root", str(d), "--apply"]), 0)
        for n in ("design-system.ts", "design-system-layout.test.ts", "design-system-freeze.test.ts", "design-system-follow.test.ts"):
            self.assertTrue((d / "scripts/design" / n).is_file(), n)

    def test_templates_hold_no_project_specific_words(self):
        for p in S.TEMPLATES.rglob("*"):
            if p.is_file():
                t = p.read_text(encoding="utf-8").lower()
                for bad in ("comic", "twin", "master", "operator"):
                    self.assertNotIn(bad, t, f"{p.name}: {bad}")

    def test_starter_is_full_and_marked(self):  # R15.6
        d = ds_repo()
        v = d / "docs/design-system/next-version"
        for n in ("ux-rules.md", "components.md", "tokens.md", "content.md", "README.md"):
            self.assertIn("starter item", r(d, f"docs/design-system/next-version/{n}"), n)
        ids = S.RULE_ID_RE.findall((v / "ux-rules.md").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(ids), 20)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual((v / "components.md").read_text(encoding="utf-8").count("\n## "), 20)
        tok = (v / "tokens.md").read_text(encoding="utf-8")
        self.assertIn("[data-theme=dark]", tok)
        self.assertIn("prefers-color-scheme: dark", tok)
        self.assertIn("- C1: starter design system from luismc-docs", (v / "CHANGES.md").read_text(encoding="utf-8"))
        # every UX id cited in components exists
        import re
        cited = set(re.findall(r"UX-\d+", (v / "components.md").read_text(encoding="utf-8")))
        self.assertLessEqual(cited, set(ids))
        # no approved action word is also retired
        content = (v / "content.md").read_text(encoding="utf-8")
        block = content.split("<!-- retired-words:start -->")[1].split("<!-- retired-words:end -->")[0]
        retired = [ln.split("|")[1].strip() for ln in block.splitlines() if ln.startswith("|")][2:]
        vocab = [ln.split("|")[1].strip() for ln in content.split("## Retired words")[0].splitlines() if ln.startswith("|")][2:]
        self.assertFalse(set(retired) & set(vocab))
        # Check is retired: no approved action word starts with it, and Review takes its place
        self.assertFalse([w_ for w_ in vocab if w_.lower().startswith("check")])
        self.assertIn("Check", retired)
        self.assertIn("Review", vocab)
        # the Wizard component carries the wizard-end rule
        comps = (v / "components.md").read_text(encoding="utf-8")
        wiz = comps.split("## 4. Wizard")[1].split("\n## 5.")[0]
        for part in ("Review", "Done", "Nothing has changed yet.", "UX-30"):
            self.assertIn(part, wiz)
        self.assertIn("UX-30", (v / "ux-rules.md").read_text(encoding="utf-8"))

    def test_styles_lists_candidates_read_only(self):
        d = project()
        w(d, "src/tokens.css", ":root { --brand: #123456; --gap: 8px; }\n")
        w(d, "tailwind.config.js", "module.exports = {}\n")
        w(d, "node_modules/x/theme.css", ":root{--no:1}\n")
        res = S.find_styles(d)
        paths = [f["path"] for f in res]
        self.assertIn("src/tokens.css", paths)
        self.assertIn("tailwind.config.js", paths)
        self.assertFalse(any("node_modules" in p for p in paths))
        props = next(f for f in res if f["path"] == "src/tokens.css")["properties"]
        self.assertEqual(props[0], {"name": "--brand", "value": "#123456"})
        self.assertEqual(S.main(["styles", "--root", str(d)]), 0)
        self.assertEqual(r(d, "src/tokens.css"), ":root { --brand: #123456; --gap: 8px; }\n")

    def test_tree_digest_ignores_line_endings(self):
        d = ds_repo()
        folder = d / "docs/design-system/next-version"
        a = S.tree_digest(folder)
        p = folder / "tokens.md"
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(S.tree_digest(folder), a)


TOKENS_MIN = """# Tokens
**Prefix:** `--ds-`
## Colour
| Token | Light | Dark | Use |
|---|---|---|---|
| `--ds-color-text` | `#000000` | `#ffffff` | text |
| `--ds-color-page` | `#ffffff` | `#000000` | page |
| `--ds-color-primary` | `#777777` | `#888888` | action |
| `--ds-color-surface` | `primary` | `#111111` | a name, not a colour |
"""


def gallery_html(tokens, components="# C\n## 1. Buttons\n- **Used for:** x\n"):
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp()) / "next-version"
    d.mkdir()
    (d / "tokens.md").write_text(tokens, encoding="utf-8")
    (d / "components.md").write_text(components, encoding="utf-8")
    return S.build_visuals(d).read_text(encoding="utf-8")


class RefreshDraftGalleryTests(unittest.TestCase):  # R15.7b
    def test_stale_rebuilds_and_fresh_does_nothing(self):
        d = ds_repo()
        self.assertEqual(S.refresh_draft_gallery(d), "")
        g = "docs/design-system/next-version/review-visuals/index.html"
        w(d, g, r(d, g).replace("gallery-script: %d" % S.GALLERY_SCRIPT_VERSION, "gallery-script: 0"))
        self.assertIn("older gallery script", S.refresh_draft_gallery(d))
        self.assertEqual(S.refresh_draft_gallery(d), "")
        (d / g).unlink()
        self.assertIn("no gallery yet", S.refresh_draft_gallery(d))

    def test_no_config_or_no_draft_does_nothing(self):
        d = ds_repo()
        (d / "docs/design-system/next-version/ux-rules.md").unlink()
        self.assertEqual(S.refresh_draft_gallery(d), "")
        self.assertEqual(S.refresh_draft_gallery(make_repo({"a": "b"})), "")

    def test_fails_open(self):
        d = ds_repo()
        (d / "docs/design-system/next-version/review-visuals/index.html").unlink()
        orig = S.build_visuals
        S.build_visuals = lambda *a, **k: 1 / 0
        try:
            self.assertEqual(S.refresh_draft_gallery(d), "")
        finally:
            S.build_visuals = orig


class GalleryTests(unittest.TestCase):
    def test_contrast_math(self):  # R15.2 WCAG 2.2
        self.assertAlmostEqual(GT.contrast("#000", "#fff"), 21.0, places=6)
        self.assertEqual(GT.ratio_text(GT.contrast("#000000", "#ffffff")), "21.0:1")
        self.assertLess(GT.contrast("#777777", "#888888"), 4.5)

    def test_swatches_and_pass_fail_marks(self):
        html = gallery_html(TOKENS_MIN)
        self.assertIn('class="swb" style="background:#000000"', html)
        self.assertIn('class="cr pass">21.0:1 pass', html)
        d = GD.Draw(GT.Tokens(TOKENS_MIN))
        self.assertIn("fail".upper(), d.mark("color-primary", "color-surface") + d.mark("color-primary", "color-page", 7.0))
        self.assertIn('cr fail', d.mark("color-primary", "color-page", 7.0))

    def test_every_starter_component_has_a_drawing(self):
        text = r(S.PLUGIN, "templates/design-system/next-version/components.md")
        secs = GD.parse_components(text)
        self.assertGreaterEqual(len(secs), 33)
        drawn = [t for _, t, _ in secs if t.lower() in GD.DRAWINGS]
        rules_only = [t for _, t, _ in secs if t.lower() in GD.RULE_SECTIONS]
        self.assertEqual(len(drawn), len(secs))  # none is listed as 'nothing to draw'
        self.assertEqual(rules_only, ["Shared component rules"])  # drawn as an annotated sample
        html = gallery_html(r(S.PLUGIN, "templates/design-system/next-version/tokens.md"), text)
        self.assertEqual(len(re.findall(r'<h3 id="component-\d+"', html)), len(secs))
        self.assertIn("every component section has a drawing", html)
        self.assertEqual(html.count('class="cr fail"'), 0)

    def test_undrawn_section_is_listed(self):
        html = gallery_html(TOKENS_MIN, "## 1. Buttons\n- x\n## 2. Mine only\n- x\n")
        self.assertIn("2. Mine only", html.split("Not drawn")[1])

    def test_missing_token_gets_fallback_label_and_gap(self):
        html = gallery_html(TOKENS_MIN)
        self.assertIn("token missing: --ds-color-surface", html)  # a name, not a colour
        self.assertIn("token missing: --ds-color-on-primary", html)  # absent
        top = html.split('id="gaps"')[1].split("</section>")[0]
        self.assertIn("--ds-color-surface", top)
        self.assertIn("--ds-color-on-primary", top)

    def test_themes_light_and_dark_or_light_only(self):  # D13
        both = gallery_html(TOKENS_MIN)
        self.assertIn('<p class="meta">dark</p>', both)
        light = gallery_html(TOKENS_MIN.replace("| Dark |", "|").replace("|---|---|---|---|", "|---|---|---|").replace(" `#ffffff` | `#000000` |", " |")
                             .replace("| `#000000` |", "|").replace("| `#111111` |", "|"))
        self.assertNotIn('<p class="meta">dark</p>', light)
        self.assertIn("No dark values were found", light)

    def test_page_loads_nothing_from_the_network(self):
        html = gallery_html(r(S.PLUGIN, "templates/design-system/next-version/tokens.md"), r(S.PLUGIN, "templates/design-system/next-version/components.md"))
        self.assertEqual(re.findall(r'(?:src|href)="https?:', html), [])
        self.assertNotIn("<script", html)
        self.assertNotIn("@import", html)

    def test_older_or_missing_script_stamp_is_stale_for_next_version(self):  # D12 DS4
        d = ds_repo()
        f = d / "docs/design-system/next-version/review-visuals/index.html"
        self.assertIn(f"<!-- gallery-script: {S.GALLERY_SCRIPT_VERSION} -->", f.read_text(encoding="utf-8"))
        f.write_text(re.sub(r"<!-- gallery-script: \d+ -->\n", "", f.read_text(encoding="utf-8")), encoding="utf-8")
        res = S.check(d)
        self.assertEqual(codes(res), ["DS4"])
        self.assertIn("built by an older gallery script, run design_system.py visuals", res[0]["message"])
        f.write_text(f.read_text(encoding="utf-8").replace("<nav>", "<!-- gallery-script: 0 -->\n<nav>", 1), encoding="utf-8")
        self.assertEqual(codes(S.check(d)), ["DS4"])
        self.assertEqual(S.main(["visuals", "--root", str(d)]), 0)
        self.assertEqual(S.check(d), [])

    def test_numbered_version_with_older_stamp_is_information_only(self):  # D12
        d = ds_repo()
        S.cmd_promote(d, args())
        f = d / "docs/design-system/v1/review-visuals/index.html"
        unlock(f)
        f.write_text(re.sub(r"<!-- gallery-script: \d+ -->\n", "", f.read_text(encoding="utf-8")), encoding="utf-8")
        appr = S.read_approvals(d)
        appr["versions"]["v1"]["digest"] = S.tree_digest(d / "docs/design-system/v1")
        S.write_approvals(d, appr)
        self.assertEqual(S.check(d), [])  # no DS2, no DS4, no request to rebuild
        self.assertEqual(len(S.gallery_info(d)), 1)
        self.assertIn("information only", S.gallery_info(d)[0])
        self.assertEqual(S.main(["visuals", "v1", "--root", str(d)]), 2)


if __name__ == "__main__":
    unittest.main()
