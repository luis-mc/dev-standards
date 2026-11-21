"""DS235c: the conformance runner against a fake updater written in Python, and the Rust and Go cores."""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates"
RUNNER_DIR = DELIVERY / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(RUNNER_DIR))
import lifecycle_conformance as C  # noqa: E402

RUNNER = RUNNER_DIR / "lifecycle_conformance.py"
DAY = 86400


class FakeUpdater:
    """A small updater that follows templates/lifecycle/CONTRACT.md. `faults` switch one behaviour off."""

    def __init__(self, faults=()):
        self.f = set(faults)
        self.selftest = True
        self.lock = threading.RLock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.dispatch("reset", {"version": "1.0.0", "paired": True, "policy": "automatic_when_idle", "window": None,
                                "channel": "stable", "idle": True, "now": C.T0, "server_url": "", "public_key": "00" * 32,
                                "seed": 1})
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _handler(self):
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                with me.lock:
                    out = me.dispatch(self.path.rsplit("/test/", 1)[-1], body)
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        return H

    # --- state
    def go(self, to):
        self.history.append({"from": self.state, "to": to, "at": self.now})
        self.state = to

    def view(self):
        return {"state": self.state, "version": self.version, "paired": self.paired, "policy": self.policy,
                "window": self.window, "channel": self.channel, "idle": self.idle, "now": self.now,
                "next_check_at": self.next_check_at, "retry_at": self.retry_at, "history": self.history}

    def row(self, kind, result, actor="updater", detail="", remote=False):
        self.rows.append({"at": self.now, "kind": kind, "actor": actor, "result": result, "detail": detail,
                          "remote": remote})

    def dispatch(self, verb, b):
        if verb == "reset":
            self.version, self.paired, self.policy, self.window = b["version"], b["paired"], b["policy"], b["window"]
            self.channel, self.idle, self.now = b["channel"], b["idle"], b["now"]
            self.server, self.pub = b["server_url"], bytes.fromhex(b["public_key"])
            self.rng = random.Random(b["seed"])
            self.state, self.history, self.rows = ("up_to_date" if self.paired else "unpaired"), [], []
            self.offered = self.skipped = None
            self.failures = self.backoff = 0
            self.retry_at = None
            self.last_check = self.last_result = None
            self.selftest = True
            self.next_check_at = self.now + 60 + self.rng.random() * 540 if (self.paired or "check_unpaired" in self.f) else None
            return self.view()
        if verb == "state":
            return self.view()
        if verb == "audit":
            return {"rows": self.rows}
        if verb == "settings":
            s = {"policy": self.policy, "window": self.window, "channel": self.channel,
                 "last_check": self.last_check, "last_result": self.last_result}
            if "settings_no_window" in self.f:
                del s["window"]
            return s
        if verb == "clock.advance":
            self.advance(b["seconds"])
        elif verb == "clock.set":
            self.now = b["now"]
        elif verb == "selftest.set":
            self.selftest = b["pass"]
        elif verb == "idle.set":
            self.idle = b["idle"]
            self.reeval()
        elif verb == "policy.set":
            self.policy, self.window = b["policy"], b["window"]
            self.reeval()
        elif verb == "pair":
            self.paired = b["paired"]
            if self.paired and self.state == "unpaired":
                self.go("up_to_date")
                self.next_check_at = self.now + 60 + self.rng.random() * 540
            elif not self.paired:
                self.go("unpaired")
                self.next_check_at = self.retry_at = None
        elif verb == "check":
            if not self.paired and "check_unpaired" not in self.f:
                return {"ran": False, "state": self.view()}
            self.do_check()
            return {"ran": True, "state": self.view()}
        elif verb == "install":
            self.install(b)
        return self.view()

    # --- timers
    def in_window(self, t):
        if not self.window or "ignore_window" in self.f:
            return True
        m = (t % DAY) // 60
        a, z = (int(x) * 60 + int(y) for x, y in (w.split(":") for w in (self.window["start"], self.window["end"])))
        return a <= m < z if a <= z else (m >= a or m < z)

    def window_open(self):
        if self.state != "waiting" or not self.window or "ignore_window" in self.f:
            return None
        h, m = (int(x) for x in self.window["start"].split(":"))
        day = self.now - self.now % DAY
        return next(t for t in (day + h * 3600 + m * 60, day + DAY + h * 3600 + m * 60) if t > self.now)

    def advance(self, seconds):
        target = self.now + seconds
        while True:
            ev = [(t, k) for t, k in ((self.next_check_at, "check"), (self.retry_at, "retry"), (self.window_open(), "window")) if t is not None and t <= target]
            if not ev:
                break
            t, k = min(ev)
            self.now = max(self.now, t)
            if k == "check":
                self.do_check()
            elif k == "retry":
                self.retry_at = None
                self.decide()
            else:
                self.decide()
        self.now = target

    # --- the work
    def fetch(self, url):
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()

    def do_check(self):
        self.last_check = self.now
        try:
            env = json.loads(self.fetch(f"{self.server}/{self.channel}/manifest.json"))
        except Exception:  # noqa: BLE001
            delays = [60, 300, 1800, 7200] if "backoff_wrong" not in self.f else [60, 300, 1800, 14400]
            self.next_check_at = self.now + delays[min(self.backoff, 3)]
            self.backoff += 1
            self.last_result = "failed"
            self.row("check", "failed")
            return
        self.backoff = 0
        iv = 21600 if "interval_8h" not in self.f else 8 * 3600
        self.next_check_at = self.now + iv * (0.8 + 0.4 * self.rng.random())
        m = env["manifest"]
        self.row("check", "ok")
        bad = None
        if "ignore_sig" not in self.f and not C.ed25519_verify(self.pub, C.canonical(m), bytes.fromhex(env["signature"])):
            bad = "bad_signature"
        elif "ignore_expiry" not in self.f and m["expires_at"] <= self.now:
            bad = "expired"
        elif "older_ok" not in self.f and C.vtuple(m["version"]) < C.vtuple(self.version):
            bad = "older_version"
        if bad:
            return self.refuse(bad)
        if C.vtuple(m["version"]) == C.vtuple(self.version):
            self.last_result = "up_to_date"
            return self.go("up_to_date")
        same = self.offered and self.offered["version"] == m["version"]
        if same and self.state == "skipped":
            return
        if same and self.state == "rolled_back" and self.retry_at is not None:
            return
        if not same:
            self.failures, self.skipped, self.retry_at = 0, None, None
        self.offered = m
        self.last_result = "available"
        self.go("available")
        self.decide()

    def refuse(self, reason):
        self.go("refused")
        self.last_result = "refused"
        self.row("refused", "refused", detail=reason)

    def decide(self):
        m = self.offered
        required = m["required"] and "required_asks" not in self.f
        ask = self.policy == "ask_first" and "ask_first_installs" not in self.f
        if required:
            return self.download("updater", False)
        if ask:
            return self.go("review")
        if self.idle and self.in_window(self.now):
            return self.download("updater", False)
        self.go("waiting")

    def reeval(self):
        if self.state == "waiting":
            self.decide()

    def install(self, b):
        if self.offered and self.state in ("review", "waiting", "available") and (b.get("click") or b.get("remote")):
            actor = b.get("actor", "")
            if "no_actor" in self.f:
                actor = ""
            self.download(actor, b.get("remote", False))

    def download(self, actor, remote):
        m = self.offered
        self.go("downloading")
        data = self.fetch(m["url"])
        self.go("verifying")
        if hashlib.sha256(data).hexdigest() != m["sha256"] and "ignore_hash" not in self.f:
            return self.refuse("bad_hash")
        self.go("installing")
        self.go("testing")
        if self.selftest:
            self.version = m["version"]
            self.go("updated")
            self.last_result = "updated"
            self.row("install", "ok", actor, remote=remote)
            self.offered = None
            return
        self.go("rolling_back")
        self.go("rolled_back")
        self.last_result = "rolled_back"
        self.row("install", "rolled_back", actor, remote=remote)
        self.row("rollback", "ok", actor, remote=remote)
        self.failures += 1
        if self.failures >= 3:
            self.skipped = m["version"]
            self.row("skip", "ok")
            self.go("skipped")
        else:
            first, second = (1800, 14400) if "retry_30min" in self.f else (3600, 14400)
            self.retry_at = self.now + (first if self.failures == 1 else second)


def run_against(faults=()):
    u = FakeUpdater(faults)
    try:
        return {r["id"]: r for r in C.run(C.HttpTransport(u.url))}
    finally:
        u.close()


class Ed25519Test(unittest.TestCase):
    def test_rfc8032_vector_1(self):
        sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(C.ed25519_public(sk).hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = C.ed25519_sign(sk, b"")
        self.assertTrue(sig.hex().startswith("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e0652"))
        self.assertTrue(C.ed25519_verify(C.ed25519_public(sk), b"", sig))
        self.assertFalse(C.ed25519_verify(C.ed25519_public(sk), b"x", sig))


class ConformanceTest(unittest.TestCase):
    def test_good_updater_passes_everything(self):
        got = run_against()
        self.assertEqual(sorted(got), sorted(i for i, _ in C.CHECKS))
        self.assertEqual({k: v["result"] for k, v in got.items() if v["result"] != "PASS"}, {}, got)

    def test_one_fault_fails_exactly_one_check(self):
        cases = {
            "ignore_sig": "LC-4", "ignore_expiry": "LC-4", "older_ok": "LC-4",
            "interval_8h": "LC-5", "backoff_wrong": "LC-5",
            "ignore_window": "LC-6", "required_asks": "LC-6",
            "retry_30min": "LC-7", "no_actor": "LC-25", "settings_no_window": "LC-26",
            "check_unpaired": "LC-28",
        }
        for fault, check in cases.items():
            with self.subTest(fault=fault):
                failed = sorted(k for k, v in run_against({fault}).items() if v["result"] == "FAIL")
                self.assertEqual(failed, [check])

    def test_ask_first_that_installs_fails_lc6(self):
        got = run_against({"ask_first_installs"})
        self.assertEqual(got["LC-6"]["result"], "FAIL")

    def test_bad_hash_fault_fails_lc3_and_lc4(self):
        failed = sorted(k for k, v in run_against({"ignore_hash"}).items() if v["result"] == "FAIL")
        self.assertEqual(failed, ["LC-3", "LC-4"])

    def test_cli_exit_and_json(self):
        u = FakeUpdater()
        try:
            r = subprocess.run([sys.executable, str(RUNNER), "--url", u.url, "--json", "--only", "LC-28"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)[0]["result"], "PASS")
        finally:
            u.close()

    def test_unreachable_exits_2(self):
        r = subprocess.run([sys.executable, str(RUNNER), "--url", "http://127.0.0.1:9"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


class TemplateTest(unittest.TestCase):
    def _copy(self, name):
        import tempfile
        dst = Path(tempfile.mkdtemp(prefix="ds235c-")) / name
        shutil.copytree(DELIVERY / "lifecycle" / name, dst, ignore=shutil.ignore_patterns("target"))
        return dst

    def _env(self):
        env = dict(os.environ)
        env["LIFECYCLE_CONFORMANCE"] = str(RUNNER)
        env["PYTHON"] = sys.executable
        return env

    @unittest.skipUnless(shutil.which("go"), "go toolchain is not installed")
    def test_go_core_passes_the_runner(self):
        d = self._copy("go")
        r = subprocess.run(["go", "test", "./..."], cwd=d, env=self._env(), capture_output=True, text=True, timeout=500)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipUnless(shutil.which("cargo"), "cargo toolchain is not installed")
    def test_rust_core_passes_the_runner(self):
        d = self._copy("rust")
        r = subprocess.run(["cargo", "test", "--quiet"], cwd=d, env=self._env(), capture_output=True, text=True, timeout=590)
        if r.returncode and "failed to " in r.stderr and ("download" in r.stderr or "index" in r.stderr or "network" in r.stderr):
            self.skipTest("cargo could not fetch crates: " + r.stderr[-200:])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_contract_lists_every_verb_the_runner_calls(self):
        text = (DELIVERY / "lifecycle" / "CONTRACT.md").read_text()
        for verb in ("reset", "clock.set", "clock.advance", "server.set", "state", "check", "install", "policy.set",
                     "idle.set", "selftest.set", "pair", "audit", "settings"):
            self.assertIn(f"`{verb}`", text)

    def test_tools_json_registers_the_runner(self):
        data = json.loads((RUNNER_DIR / "tools.json").read_text())
        self.assertIn("lifecycle-conformance", data)


if __name__ == "__main__":
    unittest.main()
