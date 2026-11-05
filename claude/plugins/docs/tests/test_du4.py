"""DU4: a lone `--`, DS4 on a task branch, link-only edits (relink), the CHANGES.md example, the version README section."""
import importlib.util
import stat
import unittest

from _helpers import *  # noqa
import design_system as S
import docs_check as C
import docs_fold as F
import docs_index as I
import docs_setup as SU
import docs_work as W
from test_design_system import args, codes, ds_repo, unlock

FEATURE = spec(version="1.3.1", body="# T\n")


def commit_all(d, msg="c"):
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", msg)


def approved_repo():
    d = ds_repo()
    S.cmd_promote(d, args())
    commit_all(d)
    return d


class LoneDashDashTests(unittest.TestCase):  # F1
    def test_note_accepts_a_lone_double_dash(self):
        d = project({"docs/features/x/spec.md": spec(fid="x", version="1.0.0", body="# T\n")})
        self.assertEqual(F.main(["note", "--root", str(d), "--", "--doc", "features/x", "--task", "T1", "--change", "minor", "--text", "t"]), 0)
        self.assertTrue(list((d / "docs/architecture/changes").glob("T1*")) or list(d.rglob("*T1*.md")))

    def test_every_script_drops_it(self):
        d = project()
        for mod, a in ((C, ["--root", str(d), "--"]), (I, ["check", "--root", str(d), "--"]), (W, ["strip", "--root", str(d), "--"]),
                       (S, ["status", "--root", str(d), "--"]), (SU, ["init", "--root", str(d), "--"])):
            try:
                rc = mod.main(a)
            except SystemExit as e:  # argparse error is exit 2
                self.fail(f"{mod.__name__} rejected a lone --: {e}")
            self.assertIsNotNone(rc)


class Ds4BranchTests(unittest.TestCase):  # F2
    def stale(self):
        d = ds_repo()
        commit_all(d)
        (d / "docs/design-system/next-version/tokens.md").write_text("# changed\n", encoding="utf-8")
        return d

    def test_default_branch_still_warns(self):
        d = self.stale()
        self.assertEqual(codes(S.check(d)), ["DS4"])

    def test_task_branch_is_information_only(self):
        d = self.stale()
        git(d, "checkout", "-q", "-b", "T1-x")
        self.assertEqual(S.check(d), [])
        self.assertTrue(any("next-version" in x and "stale" in x for x in S.gallery_info(d)))

    def test_default_branch_name_comes_from_docs_json(self):
        d = self.stale()
        git(d, "checkout", "-q", "-b", "trunk")
        self.assertEqual(S.check(d), [])  # trunk is not "main"
        w(d, "docs/docs.json", r(d, "docs/docs.json").replace('"main"', '"trunk"'))
        self.assertEqual(codes(S.check(d)), ["DS4"])

    def test_numbered_version_is_unchanged(self):
        d = approved_repo()
        git(d, "checkout", "-q", "-b", "T1-x")
        f = d / "docs/design-system/v1/tokens.md"
        unlock(f)
        f.write_text(f.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
        self.assertIn("DS4", codes(S.check(d)))


class RelinkTests(unittest.TestCase):  # F3
    def setUp(self):
        self.d = approved_repo()
        self.v1 = self.d / "docs/design-system/v1"
        self.readme = self.v1 / "README.md"
        unlock(self.readme)
        w(self.d, "docs/guide/a.md", "# a\n")
        w(self.d, "docs/guide/b.md", "# b\n")
        self.readme.write_text(self.readme.read_text(encoding="utf-8") + "\nSee [a](../../guide/a.md), `docs/guide/a.md`.\n", encoding="utf-8")
        S.write_approvals(self.d, {**S.read_approvals(self.d)})
        appr = S.read_approvals(self.d)
        appr["versions"]["v1"]["digest"] = S.tree_digest(self.v1)
        S.write_approvals(self.d, appr)
        commit_all(self.d)

    def edit(self, new_tail):
        t = self.readme.read_text(encoding="utf-8")
        self.readme.write_text(t[: t.index("\nSee [a]")] + new_tail, encoding="utf-8")

    def test_dry_run_changes_nothing(self):
        self.edit("\nSee [a](../../guide/b.md), `docs/guide/b.md`.\n")
        before = S.read_approvals(self.d)
        self.assertEqual(S.main(["relink", "v1", "--root", str(self.d)]), 0)
        self.assertEqual(S.read_approvals(self.d), before)
        self.assertIn("DS2", codes(S.check(self.d)))

    def test_link_only_edit_is_recorded_and_ds2_accepts_it(self):
        self.edit("\nSee [a](../../guide/b.md), `docs/guide/b.md`.\n")
        self.assertIn("DS2", codes(S.check(self.d)))
        self.assertEqual(S.main(["relink", "v1", "--apply", "--root", str(self.d)]), 0)
        rec = S.read_approvals(self.d)["versions"]["v1"]
        self.assertEqual(rec["relinked"], [{"date": "2026-10-31", "files": ["README.md"]}])
        self.assertEqual(rec["digest"], S.tree_digest(self.v1))
        self.assertEqual(S.check(self.d), [])
        self.assertEqual(S.check(self.d, "HEAD"), [])  # the branch diff accepts a link-only edit too

    def test_missing_target_is_refused(self):
        self.edit("\nSee [a](../../guide/gone.md), `docs/guide/a.md`.\n")
        self.assertEqual(S.main(["relink", "v1", "--apply", "--root", str(self.d)]), 2)
        self.assertNotIn("relinked", S.read_approvals(self.d)["versions"]["v1"])

    def test_text_change_is_refused(self):
        self.edit("\nSee [a](../../guide/b.md), `docs/guide/a.md`, and more words.\n")
        self.assertEqual(S.main(["relink", "v1", "--apply", "--root", str(self.d)]), 2)
        self.assertIn("DS2", codes(S.check(self.d, "HEAD")))

    def test_link_only_change_function(self):
        ok, _ = S.link_only_change(self.d, "docs/design-system/v1/README.md", '<a href="x.md">t</a>', '<a href="../../guide/a.md">t</a>')
        self.assertTrue(ok)
        ok, _ = S.link_only_change(self.d, "docs/design-system/v1/README.md", "[t](x.md)", "[u](../../guide/a.md)")
        self.assertFalse(ok)


class ChangesAndReadmeTests(unittest.TestCase):  # F4, F5
    def test_promote_writes_the_example_as_the_last_line(self):
        d = ds_repo()
        S.cmd_promote(d, args())
        lines = r(d, "docs/design-system/next-version/CHANGES.md").rstrip("\n").split("\n")
        self.assertEqual(lines[0], "# Changes from v1")
        self.assertEqual(lines[-1], "<!-- - C1: what changed (file; source) -->")
        self.assertNotRegex("\n".join(lines), r"(?m)^- C\d+")  # the example is a comment, not an entry

    def test_template_changes_ends_with_the_example(self):
        t = (S.TEMPLATES / "next-version/CHANGES.md").read_text(encoding="utf-8").rstrip("\n").split("\n")
        self.assertEqual(t[-1], "<!-- - C1: what changed (file; source) -->")

    def test_version_readme_has_the_section(self):
        t = (S.TEMPLATES / "next-version/README.md").read_text(encoding="utf-8")
        self.assertIn("## What the apps do not follow yet", t)
        self.assertIn("until the implementation is approved", (S.TEMPLATES / "README.md").read_text(encoding="utf-8"))


class JoinGalleryTests(unittest.TestCase):  # F2, join
    def join_module(self):
        import sys
        from pathlib import Path
        p = Path(__file__).resolve().parents[2] / "delivery/templates/shared/scripts/delivery"
        sys.path.insert(0, str(p))
        spec_ = importlib.util.spec_from_file_location("join_du4", p / "join.py")
        m = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(m)
        return m

    def test_rebuilds_and_commits_when_next_version_changed(self):
        import os
        j = self.join_module()
        d = ds_repo()
        commit_all(d)
        start = git(d, "rev-parse", "HEAD").stdout.strip()
        (d / "docs/design-system/next-version/tokens.md").write_text("# changed\n", encoding="utf-8")
        commit_all(d, "edit")
        os.environ["LUISMC_DOCS_WORK"] = str(S.PLUGIN / "scripts/docs_work.py")
        try:
            res = j.rebuild_draft_gallery(d, start)
            self.assertEqual(res, {"rebuilt": True})
            self.assertEqual(S.check(d), [])
            self.assertEqual(git(d, "log", "-1", "--format=%s").stdout.strip(), "Rebuild the next-version design-system gallery")
            self.assertEqual(j.rebuild_draft_gallery(d, git(d, "rev-parse", "HEAD").stdout.strip())["reason"], "next-version unchanged")
            os.environ["LUISMC_DOCS_WORK"] = str(d / "none/docs_work.py")
            (d / "docs/design-system/next-version/tokens.md").write_text("# again\n", encoding="utf-8")
            commit_all(d, "edit2")
            self.assertEqual(j.rebuild_draft_gallery(d, start)["reason"], "luismc-docs not present")
        finally:
            os.environ.pop("LUISMC_DOCS_WORK", None)


if __name__ == "__main__":
    unittest.main()
