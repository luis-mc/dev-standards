"""DL193: cargo-deny 0.20.2 argv. --offline is a top-level flag, placed before the subcommand."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
sys.path.insert(0, str(BASE / "rust" / "scripts" / "delivery"))
import rust_ci  # noqa: E402


class DenyArgv(unittest.TestCase):
    def test_exact_argv(self):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "app"
        root.mkdir()
        (root / "deny.toml").write_text("[advisories]\n")
        old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(tmp / "cache")
        os.environ["RUST_CI_CARGO"] = "fakecargo"
        calls = []
        real = rust_ci.subprocess.run

        class R:
            returncode = 0

        rust_ci.subprocess.run = lambda argv, **kw: (calls.append(list(argv)), R())[1]
        try:
            self.assertEqual(rust_ci.cmd_deny(root), 0)
        finally:
            rust_ci.subprocess.run = real
            os.environ.clear()
            os.environ.update(old)
        cfg = str(tmp / "cache" / "deny.generated.toml")
        self.assertEqual(calls[0], ["fakecargo", "deny", "--config", cfg, "fetch"])
        self.assertEqual(calls[1], ["fakecargo", "deny", "--config", cfg, "--offline", "check"])
        self.assertNotIn("--disable-fetch", calls[1])


if __name__ == "__main__":
    unittest.main()
