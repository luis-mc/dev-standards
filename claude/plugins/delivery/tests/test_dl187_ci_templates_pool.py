"""DL187: the rust and ts ci.yml integration jobs work on a pool runner (no Docker)."""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates"
RUST = (BASE / "rust" / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
TS = (BASE / "ts" / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
POOL = "contains(vars.CI_RUNS_ON || '', 'pool-')"
DSN = "postgres://postgres:postgres@localhost:5432/app_test"


def code(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def integration(text):
    start = text.index("\n  integration:")
    m = re.search(r"\n  [a-z][\w-]*:\n", text[start + 5:])
    return text[start:start + 5 + m.start()] if m else text[start:]


class PoolBoth(unittest.TestCase):
    def test_pool_expression_in_both(self):
        for text in (RUST, TS):
            self.assertIn(POOL, integration(text))

    def test_no_literal_pool_name(self):
        for text in (RUST, TS):
            self.assertNotIn("pool-main", text)
            self.assertNotRegex(code(text), r"pool-(?!'|db-env)")

    def test_service_skipped_on_pool(self):
        for text in (RUST, TS):
            job = integration(text)
            self.assertIn("image: ${{ !%s && 'postgres:17' || '' }}" % POOL, job)
            self.assertNotIn("&& '' ||", code(job))

    def test_db_env_step_guarded(self):
        for text in (RUST, TS):
            job = integration(text)
            i = job.index("name: Load the pool database env")
            self.assertIn("if: ${{ %s }}" % POOL, job[i:i + 200])
            self.assertIn("pool-db-env", job[i:])
            self.assertIn("$HOME/db.env", job[i:])
            self.assertIn("exit 1", job[i:i + 900])
            self.assertIn("GITHUB_ENV", job[i:])

    def test_non_pool_path_unchanged(self):
        for text in (RUST, TS):
            job = integration(text)
            self.assertIn("!%s && '%s' || ''" % (POOL, DSN), job)
            for line in ("POSTGRES_USER: postgres", "POSTGRES_DB: app_test",
                         "ports: ['5432:5432']", "--health-cmd pg_isready"):
                self.assertIn(line, job)


class RustSteps(unittest.TestCase):
    def test_migrations_only_where_they_exist(self):
        job = integration(RUST)
        self.assertIn("apps/*/migrations", job)
        self.assertIn("nothing to migrate", job)
        self.assertIn('sqlx migrate run --source "$d"', job)
        self.assertNotIn("\n          sqlx migrate run\n", job)

    def test_test_targets_conditional(self):
        job = integration(RUST)
        self.assertIn("cargo metadata", job)
        for name in ("integration", "route_coverage"):
            self.assertIn("if: ${{ steps.targets.outputs.%s == 'true' }}" % name, job)
            self.assertIn("cargo test --locked --test %s" % name, job)

    def test_ts_unchanged_steps(self):
        job = integration(TS)
        self.assertIn("pnpm turbo migrate", job)
        self.assertIn("pnpm vitest run --project integration", job)


if __name__ == "__main__":
    unittest.main()
