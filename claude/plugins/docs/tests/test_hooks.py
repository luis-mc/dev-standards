import io
import json
import os
import subprocess
import sys
import unittest
from _helpers import *  # noqa
import docs_index as I


def run_hook(name, cwd):
    p = subprocess.run([sys.executable, str(SCRIPTS / name)], input="{}", capture_output=True, text=True, cwd=str(cwd))
    return p.returncode, p.stdout.strip()


def proj():
    d = project({"docs/features/import/spec.md": spec(), "src/import/a.py": "x"})
    I.build(d)
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
    return d


class HookTests(unittest.TestCase):
    def test_hooks_json_wires_both_hooks(self):
        hj = json.loads((SCRIPTS.parent / "hooks/hooks.json").read_text())
        self.assertIn("hook_stop.py", json.dumps(hj["hooks"]["Stop"]))
        self.assertIn("hook_session_start.py", json.dumps(hj["hooks"]["SessionStart"]))
        for ev in hj["hooks"].values():
            for g in ev:
                for h in g["hooks"]:
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", h["command"])

    def test_session_start_gives_the_rule_when_opted_in(self):
        d = proj()
        rc, out = run_hook("hook_session_start.py", d)
        self.assertEqual(rc, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("docs_fold.py note", ctx)
        self.assertIn("Docs: none", ctx)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", ctx)

    def test_session_start_silent_without_config(self):
        d = make_repo({"a": "b"})
        self.assertEqual(run_hook("hook_session_start.py", d), (0, ""))

    def test_stop_warns_on_mapped_code_without_docs(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2")
        rc, out = run_hook("hook_stop.py", d)
        self.assertEqual(rc, 0)
        msg = json.loads(out)["systemMessage"]
        self.assertIn("docs/features/import/spec.md", msg)
        self.assertIn("Docs: none", msg)
        self.assertNotIn("decision", json.loads(out), "it warns, it does not block")

    def test_stop_silent_when_docs_follow(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2")
        w(d, "docs/features/import/changes/T1.md", "---\nchange: patch\n---\nx\n")
        self.assertEqual(run_hook("hook_stop.py", d), (0, ""))

    def test_stop_silent_without_config_and_fails_open(self):
        d = make_repo({"a": "b"})
        self.assertEqual(run_hook("hook_stop.py", d), (0, ""))
        d2 = proj()
        w(d2, "docs/docs-map.json", "{broken")
        git(d2, "checkout", "-q", "-b", "f"); w(d2, "src/import/a.py", "z")
        rc, out = run_hook("hook_stop.py", d2)
        self.assertEqual(rc, 0)

    def _counted(self, d):
        import docs_lib as D
        import hook_stop as H
        calls = []
        orig = D.git

        def spy(root, *a, **k):
            calls.append(a[0])
            return orig(root, *a, **k)
        D.git = spy
        try:
            msg = H.cached_message(d)
        finally:
            D.git = orig
        return msg, calls

    def test_stop_reuses_result_when_nothing_changed(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2")
        m1, c1 = self._counted(d)
        self.assertIn("docs/features/import/spec.md", m1)
        self.assertIn("diff", c1)
        m2, c2 = self._counted(d)
        self.assertEqual(m2, m1)
        self.assertEqual(set(c2), {"rev-parse", "status"})
        self.assertLessEqual(len(c2), 3)  # 2 with origin/<default>, 3 when only the local branch exists

    def test_stop_recomputes_when_tree_changes(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2")
        m1, _ = self._counted(d)
        self.assertTrue(m1)
        w(d, "docs/features/import/changes/T1.md", "---\nchange: patch\n---\nx\n")
        m2, c2 = self._counted(d)
        self.assertEqual(m2, "")
        self.assertIn("diff", c2)
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "more")
        m3, c3 = self._counted(d)
        self.assertEqual(m3, "")
        self.assertIn("diff", c3)

    def test_stop_recomputes_when_a_changed_file_changes_again(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "docs/features/import/changes/T1.md", "x")
        w(d, "src/import/a.py", "x=2")
        self._counted(d)
        w(d, "docs/features/import/changes/T1.md", "---\nchange: patch\n---\nx\n")  # status text unchanged
        _, c2 = self._counted(d)
        self.assertIn("diff", c2)

    def test_stop_corrupt_state_falls_back(self):
        d = proj()
        git(d, "checkout", "-q", "-b", "feat")
        w(d, "src/import/a.py", "x=2")
        (d / ".git" / "luismc-docs-stop.json").write_text("{nope")
        rc, out = run_hook("hook_stop.py", d)
        self.assertIn("systemMessage", out)


if __name__ == "__main__":
    unittest.main()
