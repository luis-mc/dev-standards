"""DL90: find_root resolves a git worktree to its main checkout; `link` sets a train's pr and head."""
import json
import tempfile
import unittest
from pathlib import Path

from _helpers import L


def _layout():
    base = Path(tempfile.mkdtemp(prefix="dl90-")).resolve()
    main = base / "app1"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
    (main / ".delivery").mkdir()
    (main / ".delivery" / "config.json").write_text("{}")
    wt = base / "app1-r21"
    (wt / "sub").mkdir(parents=True)
    (wt / ".git").write_text("gitdir: %s\n" % (main / ".git" / "worktrees" / "wt").as_posix())
    (wt / ".delivery").mkdir()
    (wt / ".delivery" / "gate-result.json").write_text("{}")
    return main, wt


class FindRootTests(unittest.TestCase):
    def test_worktree_resolves_to_main(self):
        main, wt = _layout()
        self.assertEqual(L.find_root(wt), main)
        self.assertEqual(L.find_root(wt / "sub"), main)

    def test_worktree_without_commondir_uses_parent_of_worktrees(self):
        main, wt = _layout()
        (main / ".git" / "worktrees" / "wt" / "commondir").unlink()
        self.assertEqual(L.find_root(wt), main)

    def test_normal_checkout_returns_itself(self):
        main, _ = _layout()
        (main / "src").mkdir()
        self.assertEqual(L.find_root(main / "src"), main)

    def test_delivery_with_only_logs_is_skipped(self):
        base = Path(tempfile.mkdtemp(prefix="dl90-")).resolve()
        (base / ".git").mkdir()
        (base / "a" / ".delivery" / "logs").mkdir(parents=True)
        self.assertEqual(L.find_root(base / "a"), base / "a")  # no project file anywhere: nearest .delivery
        (base / ".delivery").mkdir()
        (base / ".delivery" / "ledger.json").write_text("{}")
        self.assertEqual(L.find_root(base / "a"), base)

    def test_no_delivery_falls_back_to_git(self):
        base = Path(tempfile.mkdtemp(prefix="dl90-")).resolve()
        (base / ".git").mkdir()
        self.assertEqual(L.find_root(base), base)


class LinkTests(unittest.TestCase):
    def _root(self, *branches):
        main, _ = _layout()
        for b in branches:
            L.update(main, lambda led, b=b: L.new_train(led, b))
        return main

    def _run(self, head="release/2", oid="abc1234def"):
        def run(argv, root):
            return 0, json.dumps({"headRefName": head, "headRefOid": oid})
        return run

    def _args(self, **kw):
        import argparse
        return argparse.Namespace(**{"pr": 7, "sha": None, "branch": None, **kw})

    def test_links_by_head_branch(self):
        root = self._root("release/1", "release/2")
        self.assertEqual(L._cmd_link(root, self._args(), run=self._run()), 0)
        led = L.load(root)
        t = [x for x in led["trains"] if x["branch"] == "release/2"][0]
        self.assertEqual((t["pr"], t["ci"]["head_sha"]), (7, "abc1234def"))
        self.assertEqual(led["events"][-1]["kind"], "train.link")

    def test_links_by_branch_option_and_sha(self):
        root = self._root("release/1", "release/2")
        L._cmd_link(root, self._args(branch="release/1", sha="ffff000"), run=self._run(head="other"))
        t = [x for x in L.load(root)["trains"] if x["branch"] == "release/1"][0]
        self.assertEqual((t["pr"], t["ci"]["head_sha"]), (7, "ffff000"))

    def test_only_open_train_is_taken(self):
        root = self._root("release/1")
        # DL163: a PR whose branch no row has gets its own row, never the other branch's row
        L._cmd_link(root, self._args(), run=self._run(head="other"))
        rows = L.load(root)["trains"]
        self.assertIsNone(rows[0]["pr"])
        self.assertEqual((rows[1]["branch"], rows[1]["pr"]), ("other", 7))
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_unknown_branch_leaves_other_rows_alone(self):
        root = self._root("release/1", "release/2")
        L._cmd_link(root, self._args(), run=self._run(head="other"))
        rows = L.load(root)["trains"]
        self.assertEqual([t["pr"] for t in rows], [None, None, 7])
        self.assertEqual(len({t["id"] for t in rows}), 3)



class HooklibFindRootTests(unittest.TestCase):
    """DL90 join: hooklib.find_root (pre-tool, stop and session hooks) agrees with the ledger find_root."""

    def test_worktree_resolves_to_main_checkout(self):
        import hooklib
        base = Path(tempfile.mkdtemp())
        main = base / 'main'
        (main / '.git' / 'worktrees' / 'wt').mkdir(parents=True)
        (main / '.git' / 'worktrees' / 'wt' / 'commondir').write_text('../..', encoding='utf-8')
        (main / '.delivery').mkdir()
        (main / '.delivery' / 'config.json').write_text('{}', encoding='utf-8')
        wt = base / 'wt'
        (wt / '.delivery').mkdir(parents=True)
        (wt / '.delivery' / 'gate-result.json').write_text('{}', encoding='utf-8')
        (wt / '.git').write_text('gitdir: ' + (main / '.git' / 'worktrees' / 'wt').as_posix() + chr(10), encoding='utf-8')
        self.assertEqual(Path(hooklib.find_root({'cwd': str(wt)})).resolve(), main.resolve())
        self.assertEqual(Path(hooklib.find_root({'cwd': str(main)})).resolve(), main.resolve())

    def test_no_delivery_folder_is_none(self):
        import hooklib
        base = Path(tempfile.mkdtemp())
        (base / '.git').mkdir()
        self.assertIsNone(hooklib.find_root({'cwd': str(base)}))

if __name__ == "__main__":
    unittest.main()
