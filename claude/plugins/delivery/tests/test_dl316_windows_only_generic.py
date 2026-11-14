"""DL316 (with DL317 setup part, DL319, DL320): Windows-only pool mode, a generic pool, CI_RUNS_ON_WINDOWS, label removal,
the symbolic-link right and the PowerShell host-load task. Mocked probe; runs on Linux. No PowerShell runs."""
import json
import unittest
from unittest import mock

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P
from test_dl310_windows_runner import MACHINE, REPO, Probe as WinProbe, found, runner

LINUX_IDS = ('pool-files', 'pool-up', 'agent:', 'var:CI_RUNS_ON:', 'wslconfig', 'wsl-restart', 'verify')
RNAME = "host1-example-app"


class WfProbe(WinProbe):
    """gh_json lists workflow files; gh reads them. `wf` maps a file name to its text."""

    def __init__(self, wf=None, **kw):
        super().__init__(**kw)
        self.wf = wf or {}

    def gh_json(self, args):
        if args[-1].endswith('.github/workflows'):
            return [{"name": n} for n in self.wf], None
        return {"runners": self.runners}, None

    def gh(self, args, input=None):
        self.calls.append((["gh"] + list(args), input))
        for n, text in self.wf.items():
            if args[1].endswith('/' + n):
                return 0, text
        return 0, ""


def two_os_found(runners=()):
    f = found(runners)
    f["host"]["cpus"] = 8
    return f


def plan(f, probe, only=None, linux=(REPO,), windows=(REPO,)):
    with mock.patch.object(P, "runner_pin_problem", return_value=None):
        return P.plan(f, list(linux), list(windows), probe=probe, only=only,
                      cap={"ok": True, "mem_gib": 8, "cpus": 4})


def ids(pl):
    return [s["id"] for s in pl["steps"]]


class OnlyMode(unittest.TestCase):
    def test_only_windows_has_no_linux_pool_step(self):
        pl = plan(two_os_found(), WfProbe(), only="windows")
        for sid in ids(pl):
            self.assertFalse(sid.startswith(LINUX_IDS), sid)
        self.assertIn("winsvc:" + REPO, ids(pl))
        self.assertIn("var:CI_RUNS_ON_WINDOWS:" + REPO, ids(pl))

    def test_host_load_stays_in_both_modes(self):
        for only in ("windows", "linux", None):
            self.assertIn("host-load-task", ids(plan(two_os_found(), WfProbe(), only=only)), only)

    def test_only_linux_has_no_windows_step(self):
        with mock.patch.object(P, "pick_browsers", return_value=("none", None)), \
                mock.patch.object(P, "resolve_playwright", return_value=(None, "none")):
            pl = plan(two_os_found(), WfProbe(), only="linux")
        for sid in ids(pl):
            self.assertFalse(sid.startswith(("winsvc:", "win-", "runner-hooks", "var:CI_RUNS_ON_WINDOWS")), sid)
        self.assertIn("var:CI_RUNS_ON:" + REPO, ids(pl))

    def test_bad_value_is_refused(self):
        with self.assertRaises(ValueError):
            P.plan(two_os_found(), [], [REPO], only="mac")

    def test_non_pool_containers_are_left_with_only_windows(self):
        f = two_os_found()
        f["containers"] = [{"name": "old-runner", "pool": False}]
        self.assertNotIn("delete-container:old-runner", ids(plan(f, WfProbe(), only="windows")))
        self.assertIn("delete-container:old-runner", ids(plan(f, WfProbe(), only="linux")))


class RunsOnWindows(unittest.TestCase):
    def test_variable_is_the_generic_json_list(self):
        pl = plan(two_os_found(), WfProbe(), only="windows")
        s = next(x for x in pl["steps"] if x["id"] == "var:CI_RUNS_ON_WINDOWS:" + REPO)
        self.assertEqual((s["action"], s["name"]), ("set-variable", "CI_RUNS_ON_WINDOWS"))
        self.assertEqual(json.loads(s["value"]), ["self-hosted", "Windows", "X64", "pool-main", "repo-example-app"])

    def test_capability_label_from_machine_config_is_included(self):
        with mock.patch.object(P, "configured_generic_labels", return_value=["gpu"]):
            pl = plan(two_os_found([runner(RNAME, labels=("self-hosted", "Windows", "X64", "gpu"))]), WfProbe(), only="windows")
        s = next(x for x in pl["steps"] if x["id"] == "var:CI_RUNS_ON_WINDOWS:" + REPO)
        self.assertEqual(json.loads(s["value"]), ["self-hosted", "Windows", "X64", "pool-main", "repo-example-app", "gpu"])
        self.assertFalse([x for x in pl["steps"] if x["action"] == "remove-label"])

    def test_generic_set(self):
        g = P.generic_label_set("main")
        for l in ("self-hosted", "windows", "linux", "x64", "arm64", "pool-main"):
            self.assertIn(l, g)


class LabelRemoval(unittest.TestCase):
    LABELS = ("self-hosted", "Windows", "X64", "acme-win")

    def test_unused_label_gets_a_delete_step_naming_it(self):
        pl = plan(two_os_found([runner(RNAME, rid=9, labels=self.LABELS)]), WfProbe({"ci.yml": "runs-on: ubuntu-latest"}), only="windows")
        s = next(x for x in pl["steps"] if x["id"] == "label-remove:%s:acme-win" % REPO)
        self.assertEqual(s["title"], "Remove label acme-win from runner " + RNAME)
        self.assertTrue(s["delete"])
        self.assertIn("acme-win", s["names"][0])

    def test_used_label_gets_no_step_and_a_note_naming_the_file(self):
        pl = plan(two_os_found([runner(RNAME, labels=self.LABELS)]),
                  WfProbe({"win.yml": "runs-on: [self-hosted, acme-win]", "ci.yml": "runs-on: ubuntu-latest"}), only="windows")
        self.assertFalse([x for x in pl["steps"] if x["action"] == "remove-label"])
        self.assertTrue(any("win.yml" in n and "CI_RUNS_ON_WINDOWS" in n and "ci.yml" not in n for n in pl["notes"]))

    def test_unreadable_workflows_remove_nothing(self):
        class Blind(WfProbe):
            def gh_json(self, args):
                return None, "gh refused"
        pl = plan(two_os_found([runner(RNAME, labels=self.LABELS)]), Blind(), only="windows")
        self.assertFalse([x for x in pl["steps"] if x["action"] == "remove-label"])
        self.assertTrue(pl["notes"])

    def test_run_deletes_only_with_the_yes(self):
        pl = plan(two_os_found([runner(RNAME, rid=9, labels=self.LABELS)]), WfProbe(), only="windows")
        step = next(x for x in pl["steps"] if x["action"] == "remove-label")
        probe = WfProbe()
        ex = P.Executor(probe)
        ran = []
        mini = {"steps": [step], "refused": []}
        P.run(mini, ask=lambda s: True, ask_delete=lambda s: False, say=lambda t: None, execute=lambda s: ran.append(s) or (True, ""))
        self.assertEqual(ran, [])
        P.run(mini, ask=lambda s: True, ask_delete=lambda s: True, say=lambda t: None, execute=ex.run)
        cmd = [c for c, _ in probe.calls if "DELETE" in c][0]
        self.assertEqual(cmd[-1], "repos/%s/actions/runners/9/labels/acme-win" % REPO)


class SymlinkRight(unittest.TestCase):
    def test_rights_include_symlink_privilege(self):
        self.assertIn("SeCreateSymbolicLinkPrivilege", "\n".join(P.RIGHTS_PS))
        self.assertIn("SeCreateSymbolicLinkPrivilege", "\n".join(P.ps_account("ci-x")))

    def test_kept_runner_without_the_marker_gets_the_account_step(self):
        svc = {"name": "actions.runner.owner-example-app.host1-example-app", "kind": "windows-service",
               "folder": "C:/actions-runners/example-app", "account": ".\\ci-example-app"}
        fold = {"path": "C:/actions-runners/example-app", "agent_id": 3, "name": RNAME, "repo": REPO}
        old_env = P.windows_env_text("C:/actions-runners/example-app", MACHINE + "/runner-hooks").replace(
            "CI_RUNNER_RIGHTS=" + P.RIGHTS_MARK + "\n", "")
        probe = WfProbe(files={"C:/actions-runners/example-app/.env": old_env})
        pl = plan(found([runner(RNAME)], [svc], [fold]), probe, only="windows")
        self.assertIn("win-account:" + REPO, ids(pl))
        s = next(x for x in pl["steps"] if x["id"] == "winsvc:" + REPO)
        self.assertFalse(s["register"])  # no new password for an account that is right


class HostLoadTask(unittest.TestCase):
    def test_powershell_cmdlets_not_schtasks(self):
        pl = plan(two_os_found(), WfProbe(), only="windows")
        t = next(x for x in pl["steps"] if x["id"] == "host-load-task")
        text = "\n".join(t["printed"])
        for need in ("New-ScheduledTaskAction -Execute", "New-ScheduledTaskTrigger -AtStartup",
                     "Register-ScheduledTask -TaskName luismc-host-load", "-User SYSTEM -RunLevel Highest -Force",
                     "Start-ScheduledTask -TaskName luismc-host-load"):
            self.assertIn(need, text)
        self.assertNotIn("schtasks /Create", text)
        self.assertIn("-Argument '\"", text)

    def test_check_still_queries_schtasks(self):
        p = WinProbe()
        P.default_check({"action": "host-load-task"}, p)
        self.assertEqual(p.calls[0][0][:2], ["schtasks", "/Query"])


if __name__ == "__main__":
    unittest.main()
