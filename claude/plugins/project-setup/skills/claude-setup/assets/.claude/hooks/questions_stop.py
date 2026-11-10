#!/usr/bin/env python3
"""Stop hook: enforce the parked-questions rule (Q-1, Q-5).

Q-2 (a question asked in plain text) is no longer checked here (DL171): it lives only in
the delivery plugin's hook_stop.py.

Blocks the stop (exit 2, reason on stderr) when the final reply says questions are
parked or will be asked later, and the turn made no AskUserQuestion call. Claude then gathers every open
question and asks them in one AskUserQuestion batch.

Allowed without a block:
  - stop_hook_active is true (never loops);
  - the turn has an AskUserQuestion call;
  - agents of the wave still run, so Q-5 lets the question park
    (the project's .delivery/ledger.json has an agent in state queued/running,
    or an agent with an ETA (agent-eta) that is not finished (agent-done));
    an agent due within 60 minutes makes the hook say questions wait for its report;
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
from datetime import datetime, timezone
from pathlib import Path

OFF = {"0", "off", "false", "no"}
ASK_TOOL = "AskUserQuestion"

PARKED = re.compile(
    r"\b(i will ask|i'll ask|will ask (you )?(these |them |this |it )?later|"
    r"ask (you )?(these |them |this |it )?later|questions? (are |is |were |stay |remain )?parked|"
    r"park(ing)? (the |this |these )?questions?|"
    r"(?:there are|there's|i have|i've got|still|remaining|some|several|a few|\d+) (?!no\b|not\b|zero\b)(?:\w+ )?open questions?|"
    r"still to ask|questions? (still )?to ask|"
    r"waiting (on|for) your (decision|answer|input|reply))\b", re.I)


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


SOON_MIN = 60
NOTE = []   # a message for the owner when the stop is allowed
FINISHED = ("done", "empty", "failed", "stopped")


def _due(agent):
    """The ETA of an agent as an aware datetime, or None."""
    eta = agent.get("eta")
    raw = eta.get("due") if isinstance(eta, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        d = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def agents_running(dirs, now=None):
    """(running, soon): any agent of the wave still runs; the task of one due within SOON_MIN minutes."""
    now = now or datetime.now(timezone.utc)
    seen, running, soon = set(), False, None
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
            for a in agents if isinstance(agents, list) else []:
                if not isinstance(a, dict):
                    continue
                state = a.get("state")
                live = state in ("queued", "running") or (
                    isinstance(a.get("eta"), dict) and not a.get("done_at")
                    and state not in FINISHED)
                if not live:
                    continue
                running = True
                due = _due(a)
                if due is not None and (due - now).total_seconds() <= SOON_MIN * 60 and soon is None:
                    soon = str(a.get("task") or a.get("id") or "an agent")
    return running, soon


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
    if PARKED.search(final):
        running, soon = agents_running([data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")])
        if running:
            if soon:
                NOTE.append("Questions wait for the report of agent %s (due within %d minutes); "
                            "do not ask now." % (soon, SOON_MIN))
            return None
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
    if NOTE:
        print(json.dumps({"systemMessage": NOTE[0]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
