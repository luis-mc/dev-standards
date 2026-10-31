import json
import unittest
from _helpers import *  # noqa
import docs_lib as D
import docs_setup as S


def legacy():
    return make_repo({
        "docs/specs/import.md": "# Import wizard\n**Version:** 1.2.0\nSee [auth](./stack-auth.md#x), [guide](../guides/notes/setup.md), ![p](shot.png) and [web](https://x.y/z.md)\n```\n[code](nope.md)\n```\n",
        "docs/specs/stack-auth.md": "# Auth\n",
        "docs/specs/shot.png": "png",
        "docs/guides/notes/setup.md": "# Setup [back](../../specs/import.md)\n",
        "docs/guides/notes/release-runbook.md": "# R\n",
        "docs/guides/research/r1.md": "# Research\n",
        "docs/design/specs/web.md": "# Web design\n",
        "docs/work/agents/BRIEF.md": "# Brief\n",
        "docs/work/agents/reports/T1.md": "# Report\n",
        "docs/work/artifacts/manifest.json": "{}",
        "README.md": "See [spec](docs/specs/import.md)\n",
    })


class PlanTests(unittest.TestCase):
    def test_plan_is_dry_by_default_and_changes_nothing(self):
        d = legacy()
        before = git(d, "status", "--porcelain").stdout
        rc = S.main(["migrate", "--root", str(d)])
        self.assertEqual(rc, 0)
        self.assertEqual(git(d, "status", "--porcelain").stdout, before)
        self.assertTrue((d / "docs/specs/import.md").exists())

    def test_plan_targets(self):
        d = legacy()
        moves, findings = S.plan_moves(d, D.load_config(d), {})
        m = {x["old"]: x["new"] for x in moves}
        self.assertEqual(m["docs/specs/import.md"], "docs/features/import/spec.md")
        self.assertEqual(m["docs/specs/stack-auth.md"], "docs/architecture/stack-auth.md")
        self.assertEqual(m["docs/guides/notes/setup.md"], "docs/guides/setup.md")
        self.assertEqual(m["docs/guides/notes/release-runbook.md"], "docs/guides/runbooks/release-runbook.md")
        self.assertEqual(m["docs/guides/research/r1.md"], "docs/archive/research/r1.md")
        self.assertEqual(m["docs/design/specs/web.md"], "docs/archive/design-specs/web.md")
        self.assertEqual(m["docs/work/agents/BRIEF.md"], "AGENTS.md")
        self.assertEqual(m["docs/work/artifacts/manifest.json"], "docs/project/manifest.json")
        self.assertNotIn("docs/work/agents/reports/T1.md", m)
        self.assertTrue(any("branch-only" in f for f in findings))

    def test_override(self):
        d = legacy()
        moves, _ = S.plan_moves(d, D.load_config(d), {"docs/specs/import.md": "docs/architecture/import.md"})
        self.assertIn(("docs/specs/import.md", "docs/architecture/import.md"), [(x["old"], x["new"]) for x in moves])

    def test_apply_moves_with_git_mv_and_rewrites_links(self):
        d = legacy()
        rc = S.main(["migrate", "--root", str(d), "--apply"])
        self.assertEqual(rc, 0)
        self.assertFalse((d / "docs/specs/import.md").exists())
        spec_text = r(d, "docs/features/import/spec.md")
        self.assertIn("(../../architecture/stack-auth.md#x)", spec_text)
        self.assertIn("(../../guides/setup.md)", spec_text)
        self.assertIn("(../../architecture/shot.png)", spec_text)
        self.assertIn("https://x.y/z.md", spec_text)
        self.assertIn("[code](nope.md)", spec_text, "links in code fences stay as written")
        self.assertIn("(../features/import/spec.md)", r(d, "docs/guides/setup.md"))
        self.assertIn("(docs/features/import/spec.md)", r(d, "README.md"))
        st = git(d, "status", "--porcelain").stdout
        self.assertIn("R", st.split("\n")[0][:2] + st, "git recorded renames")
        self.assertIn("renamed", git(d, "status").stdout)

    def test_apply_adds_front_matter_stub_and_layout(self):
        d = legacy()
        S.main(["migrate", "--root", str(d), "--apply"])
        fm, _b, ok = D.parse_front_matter(r(d, "docs/features/import/spec.md"))
        self.assertTrue(ok)
        self.assertEqual(fm["id"], "import")
        self.assertEqual(fm["version"], "1.2.0")
        self.assertEqual(fm["title"], "Import wizard")
        for rel in ("docs/docs.json", "docs/README.md", "docs/overview/glossary.md", "docs/overview/quality.md"):
            self.assertTrue((d / rel).is_file(), rel)
        self.assertIn("docs/_site/", r(d, ".gitignore"))
        self.assertEqual(r(d, "AGENTS.md"), "# Brief\n", "an existing AGENTS.md (moved from BRIEF.md) is not overwritten")

    def test_apply_never_deletes_and_keeps_work_files(self):
        d = legacy()
        S.main(["migrate", "--root", str(d), "--apply"])
        self.assertTrue((d / "docs/work/agents/reports/T1.md").is_file())

    def test_collision_keeps_both_files(self):
        d = legacy()
        w(d, "docs/features/import/spec.md", "# mine\n")
        rc = S.main(["migrate", "--root", str(d), "--apply"])
        self.assertEqual(rc, 2)
        self.assertEqual(r(d, "docs/features/import/spec.md"), "# mine\n")
        self.assertTrue((d / "docs/specs/import.md").is_file())

    def test_second_run_is_a_no_op(self):
        d = legacy()
        S.main(["migrate", "--root", str(d), "--apply"])
        moves, _ = S.plan_moves(d, D.load_config(d), {})
        self.assertEqual([m for m in moves if m["old"] != m["new"]], [])

    def test_works_without_git(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        w(d, "docs/specs/a.md", "# A [b](./b.md)\n")
        w(d, "docs/specs/stack-b.md", "# B\n")
        w(d, "docs/specs/a.md", "# A [b](./stack-b.md)\n")
        (d / ".git").mkdir()  # repo_root marker without a real repo
        S.main(["migrate", "--root", str(d), "--apply"])
        self.assertTrue((d / "docs/features/a/spec.md").is_file())
        self.assertIn("(../../architecture/stack-b.md)", r(d, "docs/features/a/spec.md"))


class InitAndRecordTests(unittest.TestCase):
    def test_init_dry_run_then_apply_with_apps(self):
        d = make_repo({"README.md": "x"})
        S.main(["init", "--root", str(d)])
        self.assertFalse((d / "docs").exists())
        S.main(["init", "--root", str(d), "--apply", "--app", "web", "--app", "home", "--topic", "library"])
        cfg = json.loads(r(d, "docs/docs.json"))
        self.assertEqual(cfg["apps"], ["web", "home"])
        self.assertEqual(cfg["topics"], ["library"])
        self.assertTrue((d / "AGENTS.md").is_file())

    def test_init_does_not_overwrite(self):
        d = make_repo({"docs/README.md": "mine", "AGENTS.md": "mine"})
        S.main(["init", "--root", str(d), "--apply"])
        self.assertEqual(r(d, "docs/README.md"), "mine")
        self.assertEqual(r(d, "AGENTS.md"), "mine")

    def test_move_record(self):
        d = make_repo({"docs/work/artifacts/manifest.json": "{}", "docs/work/artifacts/content/a/decisions.json": "{}",
                       ".claude/artifacts.json": '{"record_dir": "docs/work/artifacts", "x": 1}', "docs/project/manifest.json": "mine"})
        S.main(["move-record", "--root", str(d)])
        self.assertTrue((d / "docs/work/artifacts/manifest.json").is_file(), "dry run")
        S.main(["move-record", "--root", str(d), "--apply"])
        self.assertEqual(r(d, "docs/project/manifest.json"), "mine", "existing target kept")
        self.assertTrue((d / "docs/work/artifacts/manifest.json").is_file(), "colliding file stays")
        self.assertTrue((d / "docs/project/content/a/decisions.json").is_file())
        cfg = json.loads(r(d, ".claude/artifacts.json"))
        self.assertEqual(cfg, {"record_dir": "docs/project", "x": 1})

    def test_migrate_points_the_artifacts_plugin_at_the_moved_record(self):
        d = make_repo({"docs/artifacts/manifest.json": "{}", "docs/artifacts/content/a/decisions.json": "{}",
                       ".claude/artifacts.json": '{"x": 1}'})
        S.main(["migrate", "--root", str(d), "--apply"])
        self.assertTrue((d / "docs/project/content/a/decisions.json").is_file())
        self.assertEqual(json.loads(r(d, ".claude/artifacts.json")), {"x": 1, "record_dir": "docs/project"})
        self.assertFalse((d / "docs/artifacts").exists(), "the emptied record folder is removed")


if __name__ == "__main__":
    unittest.main()
