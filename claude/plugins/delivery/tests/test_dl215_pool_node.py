"""DL215: the pool image keeps Node and corepack on PATH."""
import re
import unittest
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"


class PoolNodeTests(unittest.TestCase):
    def setUp(self):
        self.df = (POOL / "Dockerfile").read_text()

    def test_node_is_kept_at_a_permanent_path_on_path(self):
        self.assertIn("/opt/node", self.df)
        self.assertIn('ENV PATH="/opt/node/bin:${PATH}"', self.df)
        self.assertNotRegex(self.df, r"rm -rf[^\n]*/opt/node")
        self.assertNotIn("node-build", self.df)

    def test_node_install_is_not_behind_the_browser_switch(self):
        node = self.df.index("sha256sum -c -")
        browsers = self.df.index('"$POOL_BROWSERS" = "chromium"')
        self.assertLess(node, browsers)

    def test_sha256_check_is_kept(self):
        self.assertRegex(self.df, r"ARG NODE_SHA256=[0-9a-f]{64}")
        self.assertIn('echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c -', self.df)

    def test_self_check_and_no_global_corepack_enable(self):
        self.assertIn("RUN node --version && corepack --version", self.df)
        self.assertNotRegex(self.df, r"(?m)^(RUN|\s+&&).*corepack enable")

    def test_corepack_fallback_is_pinned(self):
        self.assertRegex(self.df, r"ARG COREPACK_VERSION=\d+\.\d+\.\d+")
        self.assertIn('corepack@${COREPACK_VERSION}', self.df)

    def test_install_deps_still_uses_node(self):
        self.assertIn("playwright@${PLAYWRIGHT_VERSION} install-deps chromium", self.df)


if __name__ == "__main__":
    unittest.main()
