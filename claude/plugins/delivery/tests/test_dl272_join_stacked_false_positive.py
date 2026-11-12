"""DL272 join: a branch cut from an older head is merged as any branch; only a real conflict refuses it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dl241_join_siblings import branch, commit, git, join, repo  # noqa: E402


def no_empty_conflict(tc, p):
    lines = (p.stderr + p.stdout).splitlines()
    for i, ln in enumerate(lines):
        if "conflicts with" in ln and ln.rstrip().endswith("in:"):
            tc.assertTrue(i + 1 < len(lines) and lines[i + 1].startswith("    "), "empty file list:\n" + p.stderr)


def a_two_commits(w):
    branch(w, "A", "origin/main", "a1.txt", "1\n")
    return git(w, "rev-parse", "HEAD").strip()


def advance(w, name, fname, text):
    git(w, "checkout", "-q", name)
    commit(w, fname, text, name + "-more")
    git(w, "push", "-q", "origin", name)


class Dl272(unittest.TestCase):
    def test_children_of_older_head_join_clean(self):
        w = repo()
        first = a_two_commits(w)
        advance(w, "A", "a2.txt", "2\n")
        for n in "CDE":
            branch(w, n, first, "c-%s.txt" % n, n + "\n")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "C", "D", "E")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertNotIn("skipped", p.stdout)
        no_empty_conflict(self, p)

    def test_siblings_of_older_head_touching_one_file_join_clean(self):
        w = repo()
        branch(w, "B", "origin/main", "b1.txt", "1\n")
        first = git(w, "rev-parse", "HEAD").strip()
        advance(w, "B", "b2.txt", "2\n")
        for n in "FG":
            branch(w, n, first, "f-%s.txt" % n, n + "\n")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "B", "F", "G")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        no_empty_conflict(self, p)

    def test_clean_stacked_merge_goes_through_with_info(self):
        w = repo()
        first = a_two_commits(w)
        advance(w, "A", "a1.txt", "2\n")
        branch(w, "B", first, "b1.txt", "1\n")  # holds A's old work, touches other files: stacked, no conflict
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "B")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("B was cut from an older head of A; the merge is clean", p.stdout)

    def test_real_stacked_conflict_is_refused_with_files(self):
        w = repo()
        first = a_two_commits(w)
        advance(w, "A", "a1.txt", "2\n")
        branch(w, "B", first, "a1.txt", "3\n")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "B")
        self.assertEqual(p.returncode, 3)
        self.assertIn("a1.txt", p.stderr)
        self.assertIn("older head of A", p.stderr)
        no_empty_conflict(self, p)


if __name__ == "__main__":
    unittest.main()
