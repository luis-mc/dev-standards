"""DL223: /opt/node/bin is on PATH before the build step that runs corepack enable."""
import unittest
from pathlib import Path

DF = Path(__file__).resolve().parents[1] / "templates" / "runner-pool" / "Dockerfile"


class PathBeforeCorepack(unittest.TestCase):
    def setUp(self):
        self.df = DF.read_text(encoding="utf-8")

    def test_env_path_before_enable(self):
        env = self.df.index('ENV PATH="/opt/node/bin:${PATH}"')
        self.assertLess(env, self.df.index("/opt/node/bin/corepack enable"))

    def test_env_path_before_npm_fallback(self):
        env = self.df.index('ENV PATH="/opt/node/bin:${PATH}"')
        self.assertLess(env, self.df.index("/opt/node/bin/npm install -g"))

    def test_env_path_once(self):
        self.assertEqual(self.df.count('ENV PATH="/opt/node/bin:${PATH}"'), 1)


if __name__ == "__main__":
    unittest.main()
