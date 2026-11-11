"""DL190: the integration job is a hosted/pool pair with one check name."""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates"
TEXT = {t: (BASE / t / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8") for t in ("rust", "ts")}
POOL = "contains(vars.CI_RUNS_ON || '', 'pool-')"


def job(text, key):
    start = text.index("\n  %s:\n" % key) + 1
    m = re.search(r"^  [a-z][\w-]*:\n", text[start + 3:], re.M)
    return text[start:start + 3 + m.start()] if m else text[start:]


def field(block, name):
    return re.search(r"^    %s: (.*)$" % name, block, re.M).group(1)


def steps(block):
    body = block[block.index("\n    steps:\n"):]
    return [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


class Pair(unittest.TestCase):
    def test_same_name(self):
        for text in TEXT.values():
            self.assertEqual(field(job(text, "integration"), "name"), field(job(text, "integration-pool"), "name"))

    def test_exclusive_if(self):
        for text in TEXT.values():
            host, pool = field(job(text, "integration"), "if"), field(job(text, "integration-pool"), "if")
            self.assertTrue(host.endswith(" && !%s }}" % POOL))
            self.assertTrue(pool.endswith(" && %s }}" % POOL))
            self.assertEqual(host[:-len(" && !%s }}" % POOL)], pool[:-len(" && %s }}" % POOL)])

    def test_services_only_on_hosted(self):
        for text in TEXT.values():
            self.assertIn("\n    services:\n", job(text, "integration"))
            self.assertNotIn("services", job(text, "integration-pool"))

    def test_pool_env_step_writes_github_env(self):
        script = (BASE / "runner-pool" / "pool-db-env").read_text(encoding="utf-8")
        self.assertIn('>> "$GITHUB_ENV"', script)
        for text in TEXT.values():
            p = job(text, "integration-pool")
            self.assertIn("pool-db-env", p)
            self.assertIn('>> "$GITHUB_ENV"', p)
            self.assertNotIn("DATABASE_URL:", p)

    def test_steps_after_setup_are_identical(self):
        # Everything after the pool env step in the pool job equals everything after checkout in the hosted job.
        for text in TEXT.values():
            host = steps(job(text, "integration"))
            pool = steps(job(text, "integration-pool"))
            fi = next(n for n, ln in enumerate(pool) if ln.strip() == "fi") + 1
            self.assertEqual(host[2:], pool[fi:])


class Aggregator(unittest.TestCase):
    def test_ts_e2e_waits_for_both_and_accepts_skipped(self):
        e2e = job(TEXT["ts"], "e2e")
        self.assertIn("integration, integration-pool", e2e)
        self.assertIn("needs.integration-pool.result != 'cancelled'", e2e)
        self.assertIn("""contains(fromJSON('["success","skipped"]'), needs.integration-pool.result)""", e2e)
        self.assertIn("needs.integration-pool.result }}", e2e)
        # the status loop treats skipped as fine
        self.assertIn("success|skipped) ;;", e2e)

    def test_rust_has_no_aggregator_needing_integration(self):
        self.assertNotRegex(TEXT["rust"], r"needs:.*integration")


if __name__ == "__main__":
    unittest.main()
