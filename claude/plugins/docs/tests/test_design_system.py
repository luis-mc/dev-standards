import argparse
import json
import os
import stat
import unittest

from _helpers import *  # noqa
import design_system as S
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


if __name__ == "__main__":
    unittest.main()
