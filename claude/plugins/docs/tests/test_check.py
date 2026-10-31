import json
import os
import unittest
from _helpers import *  # noqa
import docs_check as C
import docs_index as I
import docs_lib as D

GOOD = spec(body="# T\n\nSee [sec](../../architecture/sec.md#top).\n\n```mermaid\nflowchart LR\n a-->b\n```\n")


def proj(extra=None, **kw):
    d = project({"docs/features/import/spec.md": GOOD, "docs/architecture/sec.md": "# Top\n", **(extra or {})}, **kw)
    I.build(d)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    return d


def run(d, base=None, **kw):
    return C.run_checks(d, base, reference=kw.get("reference", True))


def codes(res, sev=None):
    return sorted({x["code"] for x in res if sev is None or x["severity"] == sev})


class CheckTests(unittest.TestCase):
    def test_clean_repo(self):
        d = proj()
        self.assertEqual(codes(run(d), "error"), [])
        self.assertEqual(C.main(["--root", str(d), "--base", "main"]), 0)

    def test_layout_missing(self):
        d = make_repo({"docs/x.md": "# x\n"})
        res = C.check_layout(d, D.load_config(d))
        self.assertEqual(len([x for x in res if x["code"] == "L1"]), 8)
        self.assertEqual(C.main(["--root", str(d)]), 1)

    def test_no_docs_folder_is_usage_error(self):
        self.assertEqual(C.main(["--root", str(make_repo({"a": "b"}))]), 2)

    def test_front_matter_rules(self):
        d = proj()
        w(d, "docs/features/import/spec.md", spec(fid="other", status="done", version="1.0", apps="[nope]", topics="web").replace("type: reference", "type: manual"))
        res = C.check_features(d, D.load_config(d))
        msgs = " | ".join(x["message"] for x in res)
        for want in ("must equal the folder name", "status `done`", "version `1.0`", "app `nope`", "`topics` must be a list", "type `manual`"):
            self.assertIn(want, msgs)

    def test_missing_keys_and_no_spec(self):
        d = proj()
        w(d, "docs/features/a/spec.md", "---\nid: a\n---\n# A\n")
        (d / "docs/features/b").mkdir()
        w(d, "docs/features/c/spec.md", "# no front matter\n")
        res = C.check_features(d, D.load_config(d))
        paths = {(x["path"], x["code"]) for x in res}
        self.assertIn(("docs/features/b", "F1"), paths)
        self.assertIn(("docs/features/c/spec.md", "F1"), paths)
        self.assertTrue(any("lacks `title`" in x["message"] for x in res if x["path"] == "docs/features/a/spec.md"))

    def test_links_and_anchors_and_alt(self):
        d = proj()
        w(d, "docs/guides/g.md", "# G\n[a](missing.md) [b](../architecture/sec.md#nope) [c](../architecture/sec.md#top) [d](https://x.y) ![](shot.png)\n`[e](gone.md)`\n")
        w(d, "docs/guides/shot.png", "x")
        res = C.check_links(d)
        msgs = [x["message"] for x in res if x["path"] == "docs/guides/g.md"]
        self.assertIn("broken link: missing.md", msgs)
        self.assertIn("broken anchor: ../architecture/sec.md#nope", msgs)
        self.assertTrue(any("no alt text" in m for m in msgs))
        self.assertEqual(len(msgs), 3)

    def test_source_lines(self):
        d = proj({"src/real.py": "x", "tests/t.py": "x"})
        w(d, "docs/features/import/spec.md", spec(body="# T\n```mermaid\nflowchart LR\n```\n\nSource: src/real.py, src/gone.py\n\n```\nSource: in/code/fence.py\n```\n\n## 9. How it is proven\n\n| Req | Test |\n|---|---|\n| R5.1 | `tests/t.py` |\n| R5.2 | `tests/none.py` |\n"))
        res = C.check_sources(d)
        msgs = [x["message"] for x in res]
        self.assertEqual(len(msgs), 2, msgs)
        self.assertTrue(any("src/gone.py" in m for m in msgs))
        self.assertTrue(any("R5.2" in m and "tests/none.py" in m for m in msgs))

    def test_version_table_must_match(self):
        d = proj()
        w(d, "docs/features/import/spec.md", spec(version="1.1.0", body="# T\n```mermaid\nflowchart LR\n```\n\n## Versions\n\n| Version | Date | Release | What changed | Tasks |\n|---|---|---|---|---|\n| 1.0.0 | 2026-10-01 | R1 | x | T |\n"))
        self.assertEqual(codes(C.check_versions(d, D.load_config(d))), ["V1"])
        w(d, "docs/features/import/spec.md", spec(version="1.0.0", body="# T\n```mermaid\nflowchart LR\n```\n\n## Versions\n\n| Version | Date | Release | What changed | Tasks |\n|---|---|---|---|---|\n| 1.0.0 | 2026-10-01 | R1 | x | T |\n"))
        self.assertEqual(C.check_versions(d, D.load_config(d)), [])

    def test_generated_files_must_be_fresh(self):
        d = proj()
        w(d, "docs/features/import/spec.md", GOOD.replace("status: live", "status: building"))
        self.assertIn("G1", codes(run(d), "error"))

    def test_generated_reference(self):
        d = proj()
        cfg = json.loads(r(d, "docs/docs.json"))
        cfg["generated_reference"] = [{"name": "cli", "command": "printf 'a\\nb\\n'", "output": "docs/reference/cli.md"}]
        w(d, "docs/docs.json", json.dumps(cfg))
        w(d, "docs/reference/cli.md", "a\nb\n")
        I.build(d)
        self.assertEqual([x for x in run(d) if x["code"] == "G2"], [])
        w(d, "docs/reference/cli.md", "a\nOLD\n")
        I.build(d)
        self.assertEqual(codes(run(d), "error"), ["G2"])
        self.assertEqual([x for x in run(d, reference=False) if x["code"] == "G2"], [])

    def test_map_requires_doc_note_or_docs_none(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "code only")
        res = C.check_map(d, D.load_config(d), "main")
        self.assertEqual(codes(res), ["M1"])
        self.assertEqual(res[0]["path"], "docs/features/import/spec.md")
        # a change note satisfies the map
        w(d, "docs/features/import/changes/T1.md", "---\nchange: patch\n---\nx\n")
        self.assertEqual(C.check_map(d, D.load_config(d), "main"), [])

    def test_map_docs_none_in_commit_message(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "refactor\n\nDocs: none, internal rename")
        self.assertEqual(C.check_map(d, D.load_config(d), "main"), [])

    def test_map_doc_edit_satisfies(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2\n")
        w(d, "docs/features/import/spec.md", GOOD + "\nmore\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "both")
        self.assertEqual(C.check_map(d, D.load_config(d), "main"), [])

    def test_map_uncommitted_changes_count(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/new.py", "y=1\n")
        self.assertEqual(codes(C.check_map(d, D.load_config(d), "main")), ["M1"])

    def test_map_unrelated_code_is_fine(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/other/a.py", "x\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "other")
        self.assertEqual(C.check_map(d, D.load_config(d), "main"), [])

    def test_architecture_map_with_note_dir(self):
        d = proj({"docs/architecture/sec.md": "---\nid: sec\ntitle: Sec\nversion: 0.1.0\ncode: [src/sec/**]\n---\n# Top\n", "src/sec/a.py": "x"})
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/sec/a.py", "y")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "c")
        self.assertEqual(codes(C.check_map(d, D.load_config(d), "main")), ["M1"])
        w(d, "docs/architecture/changes/sec/T1.md", "---\nchange: patch\n---\nx\n")
        self.assertEqual(C.check_map(d, D.load_config(d), "main"), [])

    def test_work_guard(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "docs/work/reports/T1.md", "# r\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "report")
        res = C.check_work_guard(d, "main")
        self.assertEqual(codes(res), ["W1"])
        self.assertEqual(C.check_work_guard(d, None), [])

    def test_ux_rules_need_a_design_system_citation(self):
        body = ("# T\n```mermaid\nflowchart LR\n```\n\n## 4. Screens and states\n\n"
                "The save button must always be blue.\n"
                "The save button uses the primary style (design system, components 15).\n"
                "The menu must never wrap. <!-- ux-ok -->\n"
                "Empty state shows a card.\n\n## 5. Functional requirements\n\nThe API must never return 500 for a button press.\n")
        d = proj()
        w(d, "docs/features/import/spec.md", spec(body=body))
        res = [x for x in C.check_features(d, D.load_config(d)) if x["code"] == "U1"]
        self.assertEqual(len(res), 1, res)
        self.assertIn("save button must always", res[0]["message"])

    def test_freshness_warnings(self):
        d = proj()
        w(d, "docs/features/import/spec.md", spec().replace("last_verified: 2026-10-30", "last_verified: 2026-01-01"))
        self.assertIn("T1", codes(C.check_freshness(d, D.load_config(d))))
        w(d, "docs/features/import/spec.md", spec().replace("last_verified: 2026-10-30\n", ""))
        self.assertTrue(any("missing" in x["message"] for x in C.check_freshness(d, D.load_config(d))))

    def test_drift_code_newer_than_doc(self):
        import subprocess
        d = project({"docs/features/import/spec.md": spec().replace("last_verified: 2026-10-30", "last_verified: 2026-02-01"), "src/import/a.py": "x=1\n"})
        def commit(msg, date):
            env = dict(os.environ, GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date)
            subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg], check=True, env=env)
        git(d, "add", "-A")
        commit("docs", "2026-01-01T10:00:00")
        self.assertFalse([x for x in C.check_freshness(d, D.load_config(d)) if x["code"] == "T2"])
        w(d, "src/import/a.py", "x=9\n")
        commit("code", "2026-10-15T10:00:00")
        res = [x for x in C.check_freshness(d, D.load_config(d)) if x["code"] == "T2"]
        self.assertEqual(len(res), 1, res)
        self.assertIn("2026-10-15", res[0]["message"])
        # verifying the doc after the code change clears it
        w(d, "docs/features/import/spec.md", spec().replace("last_verified: 2026-10-30", "last_verified: 2026-10-20"))
        self.assertFalse([x for x in C.check_freshness(d, D.load_config(d)) if x["code"] == "T2"])

    def test_strict_fails_on_warnings(self):
        d = proj()
        w(d, "docs/features/import/spec.md", spec().replace("last_verified: 2026-10-30\n", "") )
        I.build(d)
        self.assertEqual(C.main(["--root", str(d), "--base", "main", "--no-reference"]), 0)
        self.assertEqual(C.main(["--root", str(d), "--base", "main", "--no-reference", "--strict"]), 1)

    def test_json_output(self):
        d = proj()
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            C.main(["--root", str(d), "--json", "--base", "main"])
        self.assertIsInstance(json.loads(buf.getvalue()), list)


if __name__ == "__main__":
    unittest.main()
