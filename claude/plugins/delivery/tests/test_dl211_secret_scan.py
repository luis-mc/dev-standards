"""DL211: the scan covers the history of HEAD only; project-named-secret skips non-secrets."""
import unittest
from pathlib import Path

import _helpers  # noqa: F401
from test_dl186_gitleaks_config import SHARED, ROOT_CFG, load_rules, flagged

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# Built at run time so this file holds no secret-shaped line.
K = "api_" + "key"
NOT_SECRETS = [
    "  AND " + "public_" + "key = $1",
    "SELECT * FROM t WHERE public_" + "key = ?",
    "UPDATE t SET x_" + "key = NULL",
    "x_" + "key = NULL,",
    "let b = Cfg { webhook_" + "key: 1 }; let webhook_" + "key = Some(key_value);",
    "    webhook_" + "key = Some(value)",
    "svc_" + "token = Option(tok)",
    "x_" + "key = :name",
    "db_" + "pass = None",
    "my_" + "token = nil",
    "app_" + "secret = os.environ['APP_SECRET']",
    "let app_" + "key = std::env::var(\"APP_K\")",
    "const app_" + "token = process.env.APP_TOKEN",
    "public_" + "key = 'abcdefghijklmnop'",
]
SECRETS = [
    K + ' = "abc123def456ghi789"',
    "STRIPE_" + "KEY=sk_" + "live_" + "x" * 20,
    "x_" + "key = Some(\"abc123def456\")",
    "db_" + "pass = hunter2hunter2",
]


class Scan(unittest.TestCase):
    def test_every_template_limits_the_scan_to_head(self):
        files = sorted(TEMPLATES.glob("*/.github/workflows/ci.yml"))
        self.assertGreaterEqual(len(files), 4)
        for f in files:
            text = f.read_text(encoding="utf-8")
            line = [l for l in text.splitlines() if '" git --config' in l]
            self.assertEqual(len(line), 1, f.parts[-4])
            self.assertIn('--log-opts="HEAD"', line[0], f.parts[-4])

    def test_rules(self):
        for path in (SHARED, ROOT_CFG):
            rules, allow = load_rules(path)
            for l in NOT_SECRETS:
                self.assertFalse(flagged(l, rules, allow), "false positive: %r" % l)
            for l in SECRETS:
                self.assertTrue(flagged(l, rules, allow), "missed: %r" % l)


if __name__ == "__main__":
    unittest.main()
