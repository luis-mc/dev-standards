"""DL253: a heavy local entry is freed as soon as its call has ended."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from _helpers import SCRIPTS  # noqa: F401  (puts the scripts folder on sys.path)
import load_guard as G


def env():
    d = tempfile.mkdtemp(prefix="dl253-")
    return d, mock.patch.dict(os.environ, {
        "DELIVERY_MACHINE_CONFIG": os.path.join(d, "machine.json"),
        "DELIVERY_MACHINE_DIR": os.path.join(d, "machine"), "DELIVERY_IN_CONTAINER": "0",
        "DELIVERY_LOCAL_HEAVY_DIR": os.path.join(d, "heavy")})


def transcript(d, lines, name="t.jsonl"):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")
    return p


def result_line(tid, text="done"):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def data(tid, tp, **ti):
    ti.setdefault("command", "cargo test")
    return {"tool_name": "Bash", "tool_use_id": tid, "session_id": "sess1234abcd", "transcript_path": tp,
            "tool_input": ti}


class ReleaseTests(unittest.TestCase):
    def test_result_in_transcript_frees(self):
        d, e = env()
        with e:
            tp = transcript(d, [result_line("tuA")])
            self.assertTrue(G.heavy_begin(data("tuA", tp), {}))
            self.assertEqual(G.heavy_running({}), [])
            self.assertEqual(len(G.FREED), 1)

    def test_live_call_kept(self):
        d, e = env()
        with e:
            tp = transcript(d, [result_line("other")])
            G.heavy_begin(data("tuB", tp), {})
            r = G.heavy_running({})
            self.assertEqual([x["key"] for x in r], ["tuB"])
            self.assertEqual(r[0]["session"], "sess1234abcd")
            self.assertEqual(G.FREED, [])

    def test_foreground_past_timeout_freed(self):
        d, e = env()
        with e:
            tp = transcript(d, [])
            G.heavy_begin(data("tuC", tp, timeout=60000), {})
            now = time.time()
            self.assertEqual(len(G.heavy_running({}, now=now + 60 + 100)), 1)
            self.assertEqual(G.heavy_running({}, now=now + 60 + 125), [])

    def test_default_timeout_applies(self):
        d, e = env()
        with e:
            tp = transcript(d, [])
            G.heavy_begin(data("tuD", tp), {})
            now = time.time()
            self.assertEqual(len(G.heavy_running({}, now=now + 200)), 1)
            self.assertEqual(G.heavy_running({}, now=now + 250), [])

    def test_missing_transcript_freed(self):
        d, e = env()
        with e:
            G.heavy_begin(data("tuE", os.path.join(d, "gone.jsonl")), {})
            self.assertEqual(G.heavy_running({}), [])

    def test_idle_transcript_freed(self):
        d, e = env()
        with e:
            tp = transcript(d, [])
            G.heavy_begin(data("tuF", tp), {})
            old = time.time() - 3600
            os.utime(tp, (old, old))
            self.assertEqual(G.heavy_running({}), [])

    def test_background_launch_kept_then_capped(self):
        d, e = env()
        with e:
            tp = transcript(d, [result_line("tuG", "Command running in background with ID: x")])
            G.heavy_begin(data("tuG", tp, run_in_background=True), {})
            now = time.time()
            self.assertEqual(len(G.heavy_running({}, now=now + 600)), 1)
            self.assertEqual(G.heavy_running({}, now=now + 31 * 60), [])

    def test_moved_to_background_after_timeout_kept(self):
        d, e = env()
        with e:
            tp = transcript(d, [result_line("tuH", "moved to the background after its timeout")])
            G.heavy_begin(data("tuH", tp, timeout=10000), {})
            self.assertEqual(len(G.heavy_running({}, now=time.time() + 600)), 1)

    def test_refusal_shows_age_session_and_freed(self):
        d, e = env()
        with e:
            tp = transcript(d, [result_line("tuI")])
            G.heavy_begin(data("tuI", tp), {})
            live = transcript(d, [], "live.jsonl")
            G.heavy_begin(data("tuJ", live), {})
            running = G.local_running({})
            text = G.local_refusal(running, 1, "x")
            self.assertIn("min", text)
            self.assertIn("session sess1234", text)
            self.assertIn("Freed just now as ended", text)

    def test_tail_is_bounded(self):
        d, e = env()
        with e:
            p = os.path.join(d, "big.jsonl")
            with open(p, "wb") as f:
                f.write(b"x" * (G.TAIL_BYTES * 3))
            reads = []
            real = open

            def spy(*a, **k):
                fh = real(*a, **k)
                orig = fh.read
                fh.read = lambda n=-1: (reads.append(n), orig(n))[1]
                return fh
            with mock.patch("builtins.open", spy):
                G._tail(p)
            self.assertEqual(reads, [G.TAIL_BYTES])


if __name__ == "__main__":
    unittest.main()
