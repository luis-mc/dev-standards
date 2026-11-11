"""DL220: the pool image enables corepack as root, so job users need no write access."""
import re
import unittest
from pathlib import Path

DF = Path(__file__).resolve().parents[1] / "templates" / "runner-pool" / "Dockerfile"


class PoolCorepackEnable(unittest.TestCase):
    def setUp(self):
        self.df = DF.read_text(encoding="utf-8")

    def test_enable_runs_in_node_install_step(self):
        i_node = self.df.index("tar -xJf /tmp/node.tar.xz")
        i_enable = self.df.index("/opt/node/bin/corepack enable")
        self.assertGreater(i_enable, i_node)

    def test_enable_runs_as_root(self):
        i_enable = self.df.index("/opt/node/bin/corepack enable")
        users = [m.start() for m in re.finditer(r"(?m)^USER\s", self.df)]
        self.assertTrue(all(u > i_enable for u in users))

    def test_self_check_looks_for_pnpm_shim_without_download(self):
        self.assertIn("test -L /opt/node/bin/pnpm", self.df)
        self.assertNotRegex(self.df, r"(?m)^RUN.*pnpm --version")

    def test_comment_no_longer_says_workflows_only(self):
        self.assertNotIn("No `corepack enable` here", self.df)


if __name__ == "__main__":
    unittest.main()
