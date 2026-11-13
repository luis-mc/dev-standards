"""DL284: ensure_user moves a system user or group that holds an agent's id. Fakes only, no root."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_supervisor as SUP  # noqa: E402

ALPHA = {"slug": "alpha", "user": "r-alpha"}
BETA = {"slug": "beta", "user": "r-beta"}
BASE_USERS = [("root", 0, 0), ("systemd-network", 998, 998), ("nobody", 65534, 65534)]
BASE_GROUPS = [("root", 0), ("systemd-network", 998), ("systemd-journal", 999), ("kvm", 104), ("nogroup", 65534)]


def stat_for(ids):
    def stat(path):
        uid, gid = ids[path.rsplit("/", 1)[1]]
        return SimpleNamespace(st_uid=uid, st_gid=gid)
    return stat


class ClashTest(unittest.TestCase):
    def setUp(self):
        self.calls, self.logs = [], []

    def run_fn(self, argv):
        self.calls.append(argv)
        return 0

    def ensure(self, agent, ids, users, groups, exists=False, agents=None):
        names_u = {u[0] for u in users}
        names_g = {g[0] for g in groups}
        return SUP.ensure_user(agent, "/agents", run=self.run_fn, exists=lambda u: exists or u in names_u,
                               group_exists=lambda n: n in names_g, stat=stat_for(ids), log=self.logs.append,
                               users=lambda: list(users), groups=lambda: list(groups), agents=agents or [agent])

    def test_uid_held_by_systemd_network_is_moved(self):
        ids = {"alpha": (998, 1500)}
        self.assertTrue(self.ensure(ALPHA, ids, BASE_USERS, BASE_GROUPS))
        self.assertIn(["usermod", "-u", "899", "systemd-network"], self.calls)
        self.assertLess(self.calls.index(["usermod", "-u", "899", "systemd-network"]),
                        [c[0] for c in self.calls].index("useradd"))
        useradd = [c for c in self.calls if c[0] == "useradd"][0]
        self.assertEqual(useradd[useradd.index("--uid") + 1], "998")
        self.assertEqual(len([m for m in self.logs if "moved user" in m]), 1)

    def test_gid_held_by_systemd_journal_is_moved(self):
        ids = {"alpha": (1500, 999)}
        self.assertTrue(self.ensure(ALPHA, ids, BASE_USERS, BASE_GROUPS))
        names = [c[0] for c in self.calls]
        self.assertEqual(self.calls[0], ["groupmod", "-g", "899", "systemd-journal"])
        self.assertEqual(self.calls[1][:5], ["groupadd", "--system", "--gid", "999", "r-alpha"])
        self.assertEqual(names[2], "useradd")
        useradd = self.calls[2]
        self.assertEqual(useradd[useradd.index("--gid") + 1], "999")

    def test_free_id_stays_below_the_lowest_agent(self):
        ids = {"alpha": (998, 998), "beta": (500, 500)}
        self.assertTrue(self.ensure(ALPHA, ids, BASE_USERS, BASE_GROUPS, agents=[ALPHA, BETA]))
        self.assertIn(["usermod", "-u", "498", "systemd-network"], self.calls)

    def test_existing_user_with_wrong_primary_group_is_fixed(self):
        ids = {"alpha": (1500, 999)}
        users = BASE_USERS + [("r-alpha", 1500, 999)]
        self.assertTrue(self.ensure(ALPHA, ids, users, BASE_GROUPS))
        self.assertEqual(self.calls, [["groupmod", "-g", "899", "systemd-journal"],
                                      ["groupadd", "--system", "--gid", "999", "r-alpha"],
                                      ["usermod", "-g", "r-alpha", "r-alpha"]])

    def test_correct_existing_user_calls_nothing(self):
        ids = {"alpha": (1500, 1500)}
        users = BASE_USERS + [("r-alpha", 1500, 1500)]
        self.assertTrue(self.ensure(ALPHA, ids, users, BASE_GROUPS + [("r-alpha", 1500)]))
        self.assertEqual(self.calls, [])

    def test_clash_with_root_is_an_error(self):
        self.assertFalse(self.ensure(ALPHA, {"alpha": (0, 1500)}, BASE_USERS, BASE_GROUPS))
        self.assertEqual([c for c in self.calls if c[0] in ("usermod", "groupmod", "useradd")], [])
        self.assertTrue(any("protected" in m for m in self.logs))

    def test_clash_with_kvm_is_an_error(self):
        self.assertFalse(self.ensure(ALPHA, {"alpha": (1500, 104)}, BASE_USERS, BASE_GROUPS))
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.logs), 1)

    def test_clash_with_another_agent_is_an_error(self):
        users = BASE_USERS + [("r-beta", 1500, 1501)]
        ids = {"alpha": (1500, 1600), "beta": (1500, 1501)}
        self.assertFalse(self.ensure(ALPHA, ids, users, BASE_GROUPS, agents=[ALPHA, BETA]))
        self.assertEqual(self.calls, [])

    def test_no_clash_runs_the_old_commands(self):
        self.assertTrue(self.ensure(ALPHA, {"alpha": (1500, 1500)}, BASE_USERS, BASE_GROUPS))
        self.assertEqual([c[0] for c in self.calls], ["groupadd", "useradd"])
        self.assertEqual(self.logs, [])


if __name__ == "__main__":
    unittest.main()
