#!/usr/bin/env python3
"""Black-box conformance runner for a product's updater (DS235c, DELIVERYSPEC LC-3 to 7, 25, 26, 28).

Reads the project's lifecycle.json for `test_interface`, starts a fake signed update server and drives
the updater through the test interface in templates/lifecycle/CONTRACT.md. Standard library only.

  lifecycle_conformance.py [--lifecycle docs/design-system/vN/lifecycle.json] [--url URL | --cmd CMD...]
                           [--only LC-4,LC-5] [--json]

Prints PASS or FAIL with the reason for each check. Exit 0 when all selected checks pass, 1 when any fails,
2 when the interface cannot be reached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------- Ed25519 (RFC 8032, reference version)
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    r = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        s >>= 1
    return r


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(pt):
    zi = _inv(pt[2])
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(b):
    y = int.from_bytes(b, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _h(s):
    return int.from_bytes(hashlib.sha512(s).digest(), "little") % _Q


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def ed25519_sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    pub = _compress(_mul(a, _G))
    r = _h(prefix + msg)
    rs = _compress(_mul(r, _G))
    s = (r + _h(rs + pub + msg) * a) % _Q
    return rs + int.to_bytes(s, 32, "little")


def ed25519_verify(public: bytes, msg: bytes, sig: bytes) -> bool:
    if len(public) != 32 or len(sig) != 64:
        return False
    A, R = _decompress(public), _decompress(sig[:32])
    s = int.from_bytes(sig[32:], "little")
    if A is None or R is None or s >= _Q:
        return False
    h = _h(sig[:32] + public + msg)
    return _eq(_mul(s, _G), _add(R, _mul(h, A)))


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()


def vtuple(v: str):
    return tuple(int(x) for x in v.split("."))


# ---------------------------------------------------------------- fake signed update server
T0 = 1767614400  # 2026-01-05 12:00:00 UTC
DAY = 86400
STATES = ["unpaired", "up_to_date", "available", "review", "waiting", "downloading", "verifying", "refused",
          "installing", "testing", "updated", "rolling_back", "rolled_back", "skipped"]
_ANY = set(STATES)
ALLOWED = {
    "unpaired": {"up_to_date"},
    "up_to_date": {"up_to_date", "available", "refused", "waiting", "review", "downloading"},
    "available": {"review", "waiting", "downloading"},
    "review": {"downloading", "review", "up_to_date"},
    "waiting": {"downloading", "waiting"},
    "downloading": {"verifying", "refused"},
    "verifying": {"installing", "refused"},
    "installing": {"testing"},
    "testing": {"updated", "rolling_back"},
    "updated": {"up_to_date", "available", "refused", "waiting", "review", "downloading"},
    "rolling_back": {"rolled_back"},
    "rolled_back": {"waiting", "downloading", "skipped", "available", "rolled_back", "up_to_date"},
    "refused": {"refused", "up_to_date", "available", "waiting", "review", "downloading"},
    "skipped": {"skipped", "up_to_date", "available", "waiting", "review", "downloading"},
}


class FakeServer:
    def __init__(self):
        self.secret = hashlib.sha256(b"conformance-good-key").digest()
        self.other = hashlib.sha256(b"conformance-other-key").digest()
        self.public = ed25519_public(self.secret).hex()
        self.now = T0  # shadow of the updater's fake clock, set by the harness
        self.reset()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                with outer.lock:
                    path = self.path
                    if path.startswith("/pkg/"):
                        outer.pkg_requests += 1
                        body, code = outer.package(path[5:]), 200
                    elif path.endswith("/manifest.json"):
                        outer.manifest_requests += 1
                        outer.paths.append(path)
                        if outer.down:
                            body, code = b"down", 500
                        else:
                            body, code = json.dumps(outer.signed(path.split("/")[1])).encode(), 200
                    else:
                        body, code = b"no", 404
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def reset(self):
        self.lock = getattr(self, "lock", threading.RLock())
        self.version, self.required, self.fault, self.down = "1.0.0", False, None, False
        self.manifest_requests = self.pkg_requests = 0
        self.paths = []

    def package(self, version):
        return (b"tampered" if self.fault == "bad_hash" else b"package-") + version.encode()

    def signed(self, channel):
        m = {"product": "fake", "channel": channel, "version": self.version, "required": self.required,
             "expires_at": self.now - 1 if self.fault == "expired" else self.now + 7 * DAY,
             "url": f"{self.url}/pkg/{self.version}",
             "sha256": hashlib.sha256(b"package-" + self.version.encode()).hexdigest()}
        key = self.other if self.fault == "bad_sig" else self.secret
        return {"manifest": m, "signature": ed25519_sign(key, canonical(m)).hex()}

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# ---------------------------------------------------------------- transports
class Fail(Exception):
    pass


class Unreachable(Exception):
    pass


class HttpTransport:
    def __init__(self, url):
        self.url = url.rstrip("/")

    def call(self, verb, body=None):
        req = urllib.request.Request(f"{self.url}/test/{verb}", data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            raise Unreachable(f"{verb}: {e}") from e


class CliTransport:
    def __init__(self, cmd):
        self.cmd = list(cmd)

    def call(self, verb, body=None):
        try:
            r = subprocess.run(self.cmd + [verb, json.dumps(body or {})], capture_output=True, text=True, timeout=60)
            return json.loads(r.stdout)
        except Exception as e:  # noqa: BLE001
            raise Unreachable(f"{verb}: {e}") from e


class Harness:
    def __init__(self, transport, server):
        self.t, self.srv = transport, server
        self.st = {}

    def _take(self, r):
        if not isinstance(r, dict) or "error" in r:
            raise Fail(f"interface error: {r}")
        st = r.get("state", r) if isinstance(r.get("state"), dict) else r
        if "now" in st:
            self.srv.now = st["now"]
        self.st = st
        return st

    def reset(self, **kw):
        self.srv.reset()
        body = {"version": "1.0.0", "paired": True, "policy": "automatic_when_idle", "window": None,
                "channel": "stable", "idle": True, "now": T0, "server_url": self.srv.url,
                "public_key": self.srv.public, "seed": 7}
        body.update(kw)
        self.srv.now = body["now"]
        return self._take(self.t.call("reset", body))

    def state(self):
        return self._take(self.t.call("state"))

    def advance(self, seconds):
        self.srv.now += seconds
        return self._take(self.t.call("clock.advance", {"seconds": seconds}))

    def advance_to(self, when):
        return self.advance(max(0, when - self.st["now"]))

    def check(self):
        r = self.t.call("check")
        self._take(r)
        return r

    def install(self, **kw):
        return self._take(self.t.call("install", kw))

    def set(self, verb, **kw):
        return self._take(self.t.call(verb, kw))

    def audit(self):
        return self.t.call("audit").get("rows", [])

    def settings(self):
        return self.t.call("settings")

    def expect(self, what, want, got=None):
        got = self.st.get("state") if got is None else got
        if got != want:
            raise Fail(f"{what}: expected {want!r}, got {got!r}")


def need(cond, msg):
    if not cond:
        raise Fail(msg)


# ---------------------------------------------------------------- the checks
def lc3(h):
    """LC-3 every state and every transition."""
    h.reset(paired=False, policy="ask_first")
    h.expect("after reset unpaired", "unpaired")
    h.set("pair", paired=True)
    h.expect("after pair", "up_to_date")
    h.srv.version = "2.0.0"
    h.check()
    h.expect("ask_first offers a new version", "review")
    h.install(actor="user", click=True, remote=False)
    h.expect("after a click", "updated")
    h.check()
    h.expect("check after update", "up_to_date")
    h.set("policy.set", policy="automatic_when_idle", window=None)
    h.set("idle.set", idle=False)
    h.srv.version = "3.0.0"
    h.check()
    h.expect("busy updater waits", "waiting")
    h.srv.fault = "bad_hash"
    h.set("idle.set", idle=True)
    h.expect("bad hash", "refused")
    h.srv.fault = None
    h.set("selftest.set", **{"pass": False})
    h.check()
    h.expect("failed self-test", "rolled_back")
    for _ in range(6):
        if h.st["state"] == "skipped":
            break
        need(h.st.get("retry_at"), "rolled_back has no retry_at")
        h.advance_to(h.st["retry_at"])
    h.expect("after repeated failures", "skipped")
    hist = h.state().get("history") or []
    need(hist, "state has no history")
    seen = {hist[0]["from"]} | {x["to"] for x in hist}
    for x in hist:
        need(x["to"] in ALLOWED.get(x["from"], set()) or x["to"] == "unpaired", f"illegal move {x['from']} -> {x['to']}")
    missing = [s for s in STATES if s not in seen]
    need(not missing, "states never reached: " + ", ".join(missing))
    return f"{len(STATES)} states, {len(hist)} moves"


def lc4(h):
    """LC-4 refuse and log: bad signature, bad hash, expired, older."""
    for fault, version, reason in (("bad_sig", "2.0.0", "bad_signature"), ("bad_hash", "2.0.0", "bad_hash"),
                                   ("expired", "2.0.0", "expired"), (None, "0.9.0", "older_version")):
        h.reset()
        h.srv.version, h.srv.fault = version, fault
        h.check()
        h.expect(reason, "refused")
        need(h.st.get("version") == "1.0.0", f"{reason}: installed version changed to {h.st.get('version')}")
        rows = [r for r in h.audit() if r.get("kind") == "refused"]
        need(rows, f"{reason}: no refused audit row")
        need(any(r.get("detail") == reason for r in rows), f"{reason}: audit detail is {[r.get('detail') for r in rows]}")
    return "4 refusals logged"


def lc5(h):
    """LC-5 interval and backoff with the fake clock."""
    h.reset()
    first = h.st["next_check_at"] - h.st["now"]
    need(60 <= first <= 600, f"first check in {first} s, want 60 to 600")
    for i in range(10):
        before = h.srv.manifest_requests
        h.advance_to(h.st["next_check_at"])
        need(h.srv.manifest_requests == before + 1, f"cycle {i}: expected one manifest request")
        gap = h.st["next_check_at"] - h.st["now"]
        need(0.8 * 6 * 3600 <= gap <= 1.2 * 6 * 3600, f"cycle {i}: gap {gap} s outside 6 h +/- 20%")
    h.srv.down = True
    for want in (60, 300, 1800, 7200, 7200):
        h.advance_to(h.st["next_check_at"])
        gap = h.st["next_check_at"] - h.st["now"]
        need(abs(gap - want) <= 1, f"backoff gap {gap} s, want {want}")
    h.srv.down = False
    h.advance_to(h.st["next_check_at"])
    gap = h.st["next_check_at"] - h.st["now"]
    need(0.8 * 6 * 3600 <= gap <= 1.2 * 6 * 3600, f"after a good check the gap is {gap} s")
    return "interval and 1 min, 5 min, 30 min, 2 h backoff"


def lc6(h):
    """LC-6 policies."""
    h.reset(idle=False)
    h.srv.version = "2.0.0"
    h.check()
    h.expect("automatic, busy", "waiting")
    h.advance(DAY)
    h.expect("automatic, still busy after a day", "waiting")
    need(h.st["version"] == "1.0.0", "installed while not idle")
    h.set("idle.set", idle=True)
    h.expect("automatic, idle", "updated")
    need(h.st["version"] == "2.0.0", "version did not change")

    window = {"start": "02:00", "end": "05:00"}
    h.reset(window=window)
    h.srv.version = "2.0.0"
    h.check()
    h.expect("idle but outside the window", "waiting")
    h.advance(3600)
    h.expect("one hour later, still outside the window", "waiting")
    need(h.st["version"] == "1.0.0", "installed outside the window")
    h.advance_to(T0 + 15 * 3600)  # 03:00 UTC
    h.expect("inside the window", "updated")

    h.reset(policy="ask_first")
    h.srv.version = "2.0.0"
    h.check()
    h.expect("ask_first", "review")
    h.advance(2 * DAY)
    h.expect("ask_first after two days", "review")
    need(h.st["version"] == "1.0.0", "ask_first installed without a click")
    h.install(actor="user", click=True, remote=False)
    h.expect("ask_first after a click", "updated")

    for policy in ("ask_first", "automatic_when_idle"):
        h.reset(policy=policy, window=window)
        h.srv.version, h.srv.required = "2.0.0", True
        h.check()
        h.expect(f"required under {policy}", "updated")
    return "idle, window, ask_first, required"


def lc7(h):
    """LC-7 retry 1 h, 4 h, then skipped until a newer version."""
    h.reset()
    h.set("selftest.set", **{"pass": False})
    h.srv.version = "2.0.0"
    h.check()
    h.expect("first failure", "rolled_back")
    gap = (h.st.get("retry_at") or 0) - h.st["now"]
    need(gap == 3600, f"first retry in {gap} s, want 3600")
    h.advance_to(h.st["retry_at"])
    h.expect("second failure", "rolled_back")
    gap = (h.st.get("retry_at") or 0) - h.st["now"]
    need(gap == 14400, f"second retry in {gap} s, want 14400")
    h.advance_to(h.st["retry_at"])
    h.expect("third failure", "skipped")
    need(h.srv.pkg_requests == 3, f"{h.srv.pkg_requests} installs, want 3")
    h.advance(2 * DAY)
    h.expect("skipped stays", "skipped")
    need(h.srv.pkg_requests == 3, "installed again while skipped")
    h.srv.version = "3.0.0"
    h.set("selftest.set", **{"pass": True})
    h.check()
    h.expect("a newer version", "updated")
    return "1 h, 4 h, skipped, newer version installs"


def lc25(h):
    """LC-25 a remote install is audited with actor and result."""
    actor = "owner@example.test"
    h.reset(policy="ask_first")
    h.srv.version = "2.0.0"
    h.check()
    h.install(actor=actor, remote=True, click=False)
    h.expect("remote install", "updated")
    rows = [r for r in h.audit() if r.get("kind") == "install"]
    need(any(r.get("actor") == actor and r.get("result") == "ok" and r.get("remote") is True for r in rows),
         f"no install row with actor, remote and result ok: {rows}")
    h.srv.version = "3.0.0"
    h.set("selftest.set", **{"pass": False})
    h.check()
    h.install(actor=actor, remote=True, click=False)
    rows = [r for r in h.audit() if r.get("kind") == "install" and r.get("result") == "rolled_back"]
    need(any(r.get("actor") == actor for r in rows), f"failed remote install not audited with actor: {rows}")
    return "actor and result recorded"


def lc26(h):
    """LC-26 the settings read-out."""
    window = {"start": "01:00", "end": "04:00"}
    h.reset(channel="beta")
    h.set("policy.set", policy="ask_first", window=window)
    h.check()
    s = h.settings()
    for k in ("policy", "window", "channel", "last_check", "last_result"):
        need(k in s, f"settings lacks {k}")
    need(s["policy"] == "ask_first", f"policy {s['policy']!r}")
    need(s["window"] == window, f"window {s['window']!r}")
    need(s["channel"] == "beta", f"channel {s['channel']!r}")
    need(s["last_check"] == h.st["now"], f"last_check {s['last_check']!r}, want {h.st['now']}")
    need(isinstance(s["last_result"], str) and s["last_result"], f"last_result {s['last_result']!r}")
    return "policy, window, channel, last check, last result"


def lc28(h):
    """LC-28 no check while unpaired."""
    h.reset(paired=False)
    h.advance(2 * DAY)
    need(h.srv.manifest_requests == 0, f"{h.srv.manifest_requests} requests while unpaired (timer)")
    r = h.check()
    need(r.get("ran") is False, "check ran while unpaired")
    need(h.srv.manifest_requests == 0, f"{h.srv.manifest_requests} requests while unpaired (check)")
    h.expect("still unpaired", "unpaired")
    h.set("pair", paired=True)
    h.advance(600)
    need(h.srv.manifest_requests >= 1, "no check after pairing")
    return "no request while unpaired; checks resume after pairing"


CHECKS = [("LC-3", lc3), ("LC-4", lc4), ("LC-5", lc5), ("LC-6", lc6), ("LC-7", lc7), ("LC-25", lc25),
          ("LC-26", lc26), ("LC-28", lc28)]


def find_lifecycle(root: Path):
    c = sorted(root.glob("docs/design-system/v*/lifecycle.json"), key=lambda p: [int(x) if x.isdigit() else 0 for x in p.parent.name[1:].split(".")])
    return c[-1] if c else None


def make_transport(args):
    if args.url:
        return HttpTransport(args.url)
    if args.cmd:
        return CliTransport(args.cmd)
    path = Path(args.lifecycle) if args.lifecycle else find_lifecycle(Path.cwd())
    if not path or not path.is_file():
        raise Unreachable("no lifecycle.json and no --url or --cmd")
    ti = json.loads(path.read_text()).get("test_interface") or {}
    if ti.get("transport") == "http" and ti.get("url"):
        return HttpTransport(ti["url"])
    if ti.get("transport") == "cli" and ti.get("command"):
        return CliTransport(ti["command"])
    raise Unreachable(f"{path} has no usable test_interface")


def run(transport, only=None):
    srv = FakeServer()
    h = Harness(transport, srv)
    out = []
    try:
        for cid, fn in CHECKS:
            if only and cid not in only:
                continue
            try:
                out.append({"id": cid, "result": "PASS", "reason": fn(h) or ""})
            except Fail as e:
                out.append({"id": cid, "result": "FAIL", "reason": str(e)})
            except (KeyError, TypeError, ValueError) as e:
                out.append({"id": cid, "result": "FAIL", "reason": f"unexpected reply: {e!r}"})
    finally:
        srv.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lifecycle")
    ap.add_argument("--url")
    ap.add_argument("--cmd", nargs=argparse.REMAINDER)
    ap.add_argument("--only")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        transport = make_transport(args)
        transport.call("state")
        results = run(transport, set(args.only.split(",")) if args.only else None)
    except Unreachable as e:
        print(f"cannot reach the test interface: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['result']} {r['id']} {r['reason']}")
    return 1 if any(r["result"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
