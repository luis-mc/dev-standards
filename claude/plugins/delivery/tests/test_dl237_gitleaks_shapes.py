"""DL237: two more never-secret line shapes in the shipped .gitleaks.toml, and what stays caught."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _helpers  # noqa: F401
from test_dl186_gitleaks_config import SHARED, load_rules, flagged

# Built at run time so this file holds no secret-shaped line of its own.
EK = "agent_enrollment_" + "key"
WK = "webhook_" + "key"
XS = "x_" + "secret"
HIGH = "sk_" + "live_" + "a1B2c3D4e5F6g7H8i9J0"

SQL_OK = [
    "  WHERE " + EK + " = $1 AND revoked_at IS NULL",
    "  WHERE " + EK + " = ? AND revoked_at IS NULL",
    "  WHERE " + EK + " = :name AND revoked_at IS NULL",
    "  WHERE tenant_id = $1 AND " + EK + " = $2 AND revoked_at IS NULL",
    "  AND " + EK + " = $1 OR x IS NULL",
    "  AND (a IS NULL OR " + EK + " = $1)",
    "  " + EK + " = $1 LIMIT 1",
    "  " + EK + " = $12 RETURNING id",
    "  " + EK + " = $1 ORDER BY id",
    "  \"SELECT id FROM t WHERE " + EK + " = $1 AND z IS NULL\"",
    "  \"SELECT id FROM t WHERE " + EK + " = $1\"",
    "  VALUES ($1, " + EK + " = $2, $3)",
]
CALL_OK = [
    WK + " = Some(Arc::new(signer))",
    WK + ": Box::new(load(path))",
    XS + " = Arc::new(Mutex::new(inner))",
    "    pub " + WK + ": Some(Arc::new(&signer)),",
    XS + " = a::b::c(d::e(f), g)",
]
NOT_ALLOWED = [
    # a quoted high-entropy string anywhere on the line
    "  WHERE " + EK + " = $1 AND tok = '" + HIGH + "'",
    "  WHERE x = '" + HIGH + "' AND " + EK + " = $1 AND y IS NULL",
    "  WHERE " + EK + " = $1 AND z = \"" + HIGH + "\"",
    XS + " = \"" + HIGH + "\"",
    # a bare token after =
    "  WHERE " + EK + " = $1 AND other_" + "key = hunter2hunter2",
    "  WHERE other_" + "key = hunter2hunter2 AND " + EK + " = $1 AND y IS NULL",
    "  " + EK + " = " + HIGH + " AND y IS NULL",
    "  " + EK + " = $1x9Zq7Lm2 AND y IS NULL",
    # a string literal argument
    WK + " = Some(\"" + HIGH + "\")",
    WK + " = Some(Arc::new(\"" + HIGH + "\"))",
    WK + ": Box::new(load(\"" + HIGH + "\"))",
    XS + " = Arc::new('" + HIGH + "')",
    # a bare token, or a second assignment on the same line
    "STRIPE_" + "KEY=" + HIGH,
    WK + " = " + HIGH,
    WK + " = Some(Arc::new(signer)); other_" + "key = hunter2hunter2",
    WK + " = Some(Arc::new(signer)), other_" + "token: '" + HIGH + "'",
    # first call argument is not an identifier path
    WK + " = Some(12345678abcdef(x))",
]


def shape_regexes():
    rules, allow = load_rules(SHARED)
    sql = [a for a in allow if "RETURNING" in a.pattern]
    call = [a for a in allow if "RETURNING" not in a.pattern and a.pattern.endswith("[^'\"=]*$")]
    return rules, allow, sql, call


class Shapes(unittest.TestCase):
    def test_regexes_are_found_and_re2_safe(self):
        _, _, sql, call = shape_regexes()
        self.assertEqual((len(sql), len(call)), (1, 1))
        for rx in sql + call:
            for bad in ("(?=", "(?!", "(?<=", "(?<!"):
                self.assertNotIn(bad, rx.pattern)
            self.assertNotRegex(rx.pattern, r"\\[1-9]")  # no backreference

    def test_sql_shape(self):
        _, _, sql, _ = shape_regexes()
        for l in SQL_OK:
            self.assertTrue(sql[0].search(l), "sql shape missed: %r" % l)
        for l in NOT_ALLOWED:
            self.assertFalse(sql[0].search(l), "sql shape too wide: %r" % l)

    def test_call_shape(self):
        _, _, _, call = shape_regexes()
        for l in CALL_OK:
            self.assertTrue(call[0].search(l), "call shape missed: %r" % l)
        for l in NOT_ALLOWED:
            self.assertFalse(call[0].search(l), "call shape too wide: %r" % l)

    def test_whole_config(self):
        rules, allow, _, _ = shape_regexes()
        for l in SQL_OK + CALL_OK:
            self.assertFalse(flagged(l, rules, allow), "still flagged: %r" % l)
        for l in NOT_ALLOWED:
            # lines that no rule matches at all prove nothing here; the rest must stay flagged
            if any(rx.search(l) for rx in rules.values()):
                self.assertTrue(flagged(l, rules, allow), "allowed: %r" % l)

    @unittest.skipUnless(shutil.which("gitleaks") or os.environ.get("GITLEAKS_BIN"), "gitleaks not installed")
    def test_real_gitleaks(self):
        exe = os.environ.get("GITLEAKS_BIN") or shutil.which("gitleaks")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ok").mkdir()
            (d / "bad").mkdir()
            (d / "ok" / "a.txt").write_text("\n".join(SQL_OK + CALL_OK) + "\n", encoding="utf-8")
            for i, l in enumerate(NOT_ALLOWED):
                (d / "bad" / ("n%d.txt" % i)).write_text(l + "\n", encoding="utf-8")

            def scan(path):
                return subprocess.run(
                    [exe, "dir", str(path), "--config", str(SHARED), "--no-banner", "--exit-code", "7"],
                    capture_output=True, text=True, timeout=120).returncode

            self.assertEqual(scan(d / "ok"), 0)
            rules, allow, _, _ = shape_regexes()
            for i, l in enumerate(NOT_ALLOWED):
                if any(rx.search(l) for rx in rules.values()):
                    self.assertEqual(scan(d / "bad" / ("n%d.txt" % i)), 7, "not caught: %r" % l)


if __name__ == "__main__":
    unittest.main()
