"""DL208: Stop hooks read the transcript from the end, in blocks, and stay small."""
import importlib.util
import json
import os
import tempfile
import tracemalloc
import unittest
from pathlib import Path

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import hook_stop as S

ROOT = Path(__file__).resolve().parents[4]
QS = ROOT / "claude/plugins/project-setup/skills/claude-setup/assets/.claude/hooks/questions_stop.py"
spec = importlib.util.spec_from_file_location("questions_stop_dl208", QS)
Q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Q)


def old_read_turn(path):
    entries = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    start = 0
    for i, e in enumerate(entries):
        msg = e.get("message") if isinstance(e, dict) else None
        if e.get("type") != "user" or not isinstance(msg, dict):
            continue
        c = msg.get("content")
        if isinstance(c, str) and c.strip():
            start = i + 1
        elif isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "text" for x in c):
            start = i + 1
    texts, asked = [], False
    for e in entries[start:]:
        msg = e.get("message") if isinstance(e, dict) else None
        if e.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        c = msg.get("content")
        if isinstance(c, str):
            texts.append(c)
            continue
        for x in c if isinstance(c, list) else []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use" and x.get("name") == "AskUserQuestion":
                asked = True
            elif x.get("type") == "text":
                texts.append(x.get("text", ""))
    return "\n\n".join(texts), asked


def user(t):
    return json.dumps({"type": "user", "message": {"role": "user", "content": t}})


def user_parts(t):
    return json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": t}]}})


def tool_result():
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}})


def asst(*parts):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(parts)}})


def text(t):
    return {"type": "text", "text": t}


ASK = {"type": "tool_use", "name": "AskUserQuestion", "input": {}}
FILLER = user("old " + "x" * 1000)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, lines, end="\n", name="t.jsonl"):
        p = os.path.join(self.dir.name, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + end)
        return p


class Small(Base):
    def lines(self):
        return [user("first"), asst(text("a1")), user_parts("second"),
                asst(text("I will ask later"), ASK), tool_result(), "not json",
                asst(text("done"))]

    def test_same_as_old(self):
        p = self.write(self.lines())
        self.assertEqual(Q.read_turn(p), old_read_turn(p))
        self.assertEqual(Q.read_turn(p), ("I will ask later\n\ndone", True))

    def test_small_blocks(self):
        p = self.write(self.lines())
        self.assertEqual(Q.read_turn(p, block=7), old_read_turn(p))

    def test_no_final_newline(self):
        p = self.write(self.lines(), end="")
        self.assertEqual(Q.read_turn(p), old_read_turn(p))

    def test_ask_in_middle(self):
        p = self.write([user("q"), asst(text("x"), ASK), tool_result(), asst(text("y"))])
        self.assertTrue(Q.read_turn(p)[1])

    def test_no_user_message(self):
        p = self.write([asst(text("only"))])
        self.assertEqual(Q.read_turn(p), ("only", False))

    def test_empty_file(self):
        p = self.write([], end="")
        self.assertEqual(Q.read_turn(p), ("", False))

    def test_cap_fails_open(self):
        p = self.write([user("q")] + [asst(text("z" * 1000))] * 50)
        self.assertEqual(Q.read_turn(p, cap=10_000), ("", True))

    def test_delivery_last_text(self):
        p = self.write([user("q"), asst(text("one")), asst({"type": "tool_use", "name": "Bash"}), tool_result()])
        self.assertEqual(S.last_assistant_text({"transcript_path": p}), "one")
        self.assertEqual(S.last_assistant_text({"transcript_path": p + ".none"}), "")


class Big(Base):
    def test_big_file_memory(self):
        p = os.path.join(self.dir.name, "big.jsonl")
        line = (user("old " + "x" * 1000) + "\n").encode()
        chunk = line * 1000
        with open(p, "wb") as f:
            for _ in range(200):
                f.write(chunk)
            f.write((user("last request") + "\n").encode())
            f.write((asst(text("short reply"), ASK) + "\n").encode())
            f.write((asst(text("final")) + "\n").encode())
        self.assertGreater(os.path.getsize(p), 190 * 1024 * 1024)
        tracemalloc.start()
        try:
            res = Q.read_turn(p)
            res2 = S.last_assistant_text({"transcript_path": p})
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        print("peak bytes:", peak)
        self.assertEqual(res, ("short reply\n\nfinal", True))
        self.assertEqual(res2, "final")
        self.assertLess(peak, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
