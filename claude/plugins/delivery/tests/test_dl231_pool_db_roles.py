"""DL231: declared NOLOGIN database roles."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "templates" / "runner-pool" / "pool_agents.py"
spec = importlib.util.spec_from_file_location("pool_agents_dl231", SRC)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class R:
    returncode, stdout, stderr = 0, "", ""


class Sql(unittest.TestCase):
    def test_zero_roles(self):
        self.assertEqual(A.role_sql("u_app", []), "")

    def test_one_role(self):
        sql = A.role_sql("u_app", ["app_role"])
        self.assertIn("IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role')", sql)
        self.assertIn("CREATE ROLE app_role NOLOGIN", sql)
        self.assertIn("GRANT app_role TO u_app WITH ADMIN OPTION;", sql)

    def test_two_roles(self):
        sql = A.role_sql("u_app", ["app_role", "maint_role"])
        self.assertEqual(sql.count("CREATE ROLE"), 2)
        self.assertEqual(sql.count("WITH ADMIN OPTION"), 2)
        self.assertEqual(sql.count("IF NOT EXISTS"), 2)


class Names(unittest.TestCase):
    def test_bad_names_refused(self):
        for bad in ("App", "a-b", "1abc", "", "a" * 64, "x; DROP", "postgres", "pg_read_all_data", "public", 5):
            with self.assertRaises(A.PoolError, msg=repr(bad)):
                A.check_db_roles("one", [bad], [])

    def test_good_names(self):
        self.assertEqual(A.check_db_roles("one", ["a_1", "a" * 63, "a_1"], []), ["a_1", "a" * 63])

    def test_collision_across_repos(self):
        agents = [{"slug": "two", "db_roles": ["app_role"]}]
        with self.assertRaises(A.PoolError) as c:
            A.check_db_roles("one", ["app_role"], agents)
        self.assertIn("one", str(c.exception))
        self.assertIn("two", str(c.exception))

    def test_collision_with_login(self):
        with self.assertRaises(A.PoolError):
            A.check_db_roles("one", ["u_two"], [{"slug": "two"}])
        with self.assertRaises(A.PoolError):
            A.check_db_roles("one", ["u_one"], [])

    def test_own_roles_ok_on_rerun(self):
        self.assertEqual(A.check_db_roles("one", ["app_role"], [{"slug": "one", "db_roles": ["app_role"]}]), ["app_role"])


class AddAgent(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.sql = []

    def run_(self, argv, **kw):
        if kw.get("input"):
            self.sql.append(kw["input"])
        return R()

    def add(self, slug, roles):
        A.add_agent(slug, "owner/example-app", "T", "main", True, self.file, self.d, self.run_, db_roles=roles)

    def test_roles_stored_and_run(self):
        self.add("app1", ["app_role", "maint_role"])
        self.assertIn("CREATE ROLE maint_role NOLOGIN", "\n".join(self.sql))
        self.assertEqual(json.loads(Path(self.file).read_text())["agents"][0]["db_roles"], ["app_role", "maint_role"])

    def test_no_roles_no_sql_no_key(self):
        self.add("app1", [])
        self.assertNotIn("NOLOGIN", "\n".join(self.sql))
        self.assertNotIn("db_roles", json.loads(Path(self.file).read_text())["agents"][0])

    def test_second_repo_collision_refused(self):
        self.add("app1", ["app_role"])
        with self.assertRaises(A.PoolError):
            self.add("app2", ["app_role"])

    def test_rerun_keeps_and_adds(self):
        self.add("app1", ["app_role"])
        self.add("app1", ["maint_role"])
        self.assertEqual(json.loads(Path(self.file).read_text())["agents"][0]["db_roles"], ["app_role", "maint_role"])


if __name__ == "__main__":
    unittest.main()
