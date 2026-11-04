#!/usr/bin/env python3
"""Stop hook: enforce the clarifying-questions rule (Q-1, Q-2).

Blocks the stop (exit 2, reason on stderr) when the final reply
  1. asks the owner something in plain text: the last paragraph ends with a
     question mark addressed to the owner, or lists options to pick from; or
  2. says questions are parked or will be asked later,
and the turn made no AskUserQuestion call. Claude then gathers every open
question and asks them in one AskUserQuestion batch.

Allowed without a block:
  - stop_hook_active is true (never loops);
  - the turn has an AskUserQuestion call;
  - point 2 only: agents of the wave still run, so Q-5 lets the question park
    (the project's .delivery/ledger.json has an agent in state queued/running);
  - questions inside code blocks, inline code or quoted ("> ") lines;
  - any error: the hook fails open.

Input: the Stop JSON on stdin (last_assistant_message, transcript_path,
stop_hook_active, cwd).

Turn it off: set CLAUDE_QUESTIONS_STOP=off in the settings `env` block or the
shell, or set `"questionsStop": "off"` in ~/.claude/settings.json, or delete
the Stop entry that runs this file.

Python 3, standard library only; works on Windows and Linux.
"""
import json
import os
import re
import sys
from pathlib import Path

OFF = {"0", "off", "false", "no"}
ASK_TOOL = "AskUserQuestion"

# A question mark addressed to the owner: second person, or the agent asking leave.
ADDRESSED = re.compile(
    r"\b(you|your|yours|should i|shall i|can i|may i|do i|want me|would it help|"
    r"which (one|option|of)|let me know|prefer)\b", re.I)
PARKED = re.compile(
    r"\b(i will ask|i'll ask|will ask (you )?(these |them |this |it )?later|"
    r"ask (you )?(these |them |this |it )?later|parked|park(ing)? (the |this |these )?questions?|"
    r"open questions?|still to ask|questions? (still )?to ask|"
    r"waiting (on|for) your (decision|answer|input|reply))\b", re.I)
CUE = re.compile(
    r"\b(which|choose|pick|select|prefer|option|decide|your call|let me know)\b", re.I)
ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,2}[.)]|\(?[A-Da-d][.)])\s+\S")
OPTION_LINE = re.compile(r"^\s*(?:\*\*)?option\s+[A-Za-z0-9]\b", re.I)


def disabled(home):
    if os.environ.get("CLAUDE_QUESTIONS_STOP", "").strip().lower() in OFF:
        return True
    try:
        data = json.loads((Path(home) / ".claude" / "settings.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if str(data.get("questionsStop", "")).strip().lower() in OFF:
                return True
            env = data.get("env")
            if isinstance(env, dict) and str(env.get("CLAUDE_QUESTIONS_STOP", "")).strip().lower() in OFF:
                return True
    except Exception:
        pass
    return False


def strip_noise(text):
    """Drop fenced code, inline code and quoted lines, so they never count."""
    text = re.sub(r"```.*?(```|\Z)", "", text, flags=re.S)
    text = re.sub(r"~~~.*?(~~~|\Z)", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def blocks(text):
    return [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def plain_question(text):
    """True when the last paragraph asks the owner something."""
    paras = blocks(text)
    if not paras:
        return False
    last = paras[-1]
    lines = [ln for ln in last.splitlines() if ln.strip()]
    items = [ln for ln in lines if ITEM.match(ln) or OPTION_LINE.match(ln)]
    if len(items) >= 2:
        head = [ln for ln in lines if ln not in items]
        if len(items) == len(lines) and len(paras) > 1:
            head = [paras[-2]]
        return bool(CUE.search(" ".join(head)))
    tail = lines[-1].rstrip().rstrip("*_)\"'” ")
    return tail.endswith("?") and bool(ADDRESSED.search(last))


def read_turn(path):
    """(assistant text, asked) for the turn after the last real user message."""
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
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            start = i + 1
        elif isinstance(content, list) and any(
                isinstance(c, dict) and c.get("type") == "text" for c in content):
            start = i + 1
    texts, asked = [], False
    for e in entries[start:]:
        msg = e.get("message") if isinstance(e, dict) else None
        if e.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        for c in content if isinstance(content, list) else []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") == ASK_TOOL:
                asked = True
            elif c.get("type") == "text":
                texts.append(c.get("text", ""))
    return "\n\n".join(texts), asked


def agents_running(dirs):
    seen = set()
    for d in dirs:
        if not d:
            continue
        p = Path(d)
        for cand in [p, *list(p.parents)[:6]]:
            f = cand / ".delivery" / "ledger.json"
            if f in seen:
                continue
            seen.add(f)
            try:
                ledger = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            agents = ledger.get("agents") if isinstance(ledger, dict) else None
            if isinstance(agents, list) and any(
                    isinstance(a, dict) and a.get("state") in ("queued", "running") for a in agents):
                return True
    return False


def decide(data, home):
    """The block reason, or None to allow."""
    if data.get("stop_hook_active") or disabled(home):
        return None
    text, asked = data.get("last_assistant_message") or "", False
    path = data.get("transcript_path")
    if path and os.path.isfile(path):
        turn_text, asked = read_turn(path)
        text = text or turn_text
    if asked or not isinstance(text, str) or not text.strip():
        return None
    final = strip_noise(text)
    if plain_question(final):
        return ("Q-2: you asked the owner a question in plain text. Gather every open question "
                "and ask them in one AskUserQuestion batch (several calls when more than 4). "
                "Each question carries its own context.")
    if PARKED.search(final) and not agents_running([data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")]):
        return ("Q-1: you said questions are parked or will be asked later, but no agent of this "
                "wave still runs (Q-5). Gather every open question and ask them now in one "
                "AskUserQuestion batch (several calls when more than 4). Each question carries "
                "its own context.")
    return None


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        reason = decide(data if isinstance(data, dict) else {}, os.path.expanduser("~"))
    except Exception:
        return 0
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
