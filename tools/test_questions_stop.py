#!/usr/bin/env python3
"""SO6: the questions Stop hook (Q-1, Q-2) against recorded inputs, plus the claude-setup wiring.
No network. Run: python3 tools/test_questions_stop.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "claude/plugins/project-setup/skills/claude-setup"
HOOK = SKILL / "assets/.claude/hooks/questions_stop.py"


def run(data, env=None, home=None):
    e = dict(os.environ)
    e.pop("CLAUDE_QUESTIONS_STOP", None)
    e["HOME"] = e["USERPROFILE"] = home or tempfile.mkdtemp()
    e.update(env or {})
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), capture_output=True,
                       text=True, env=e)
    return p.returncode, p.stderr


def transcript(tmp, ask=False):
    rows = [{"type": "user", "message": {"role": "user", "content": "do it"}}]
    content = [{"type": "text", "text": "working"}]
    if ask:
        content.append({"type": "tool_use", "name": "AskUserQuestion", "input": {}})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": content}})
    rows.append({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": "ok"}]}})
    p = Path(tmp) / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(p)


def main():
    errors = []
    tmp = tempfile.mkdtemp()

    def expect(name, code, data, **kw):
        rc, err = run(data, **kw)
        if rc != code:
            errors.append(f"{name}: exit {rc}, wanted {code} ({err.strip()})")
        elif code == 2 and "AskUserQuestion" not in err:
            errors.append(f"{name}: reason does not name AskUserQuestion")

    expect("plain question at end", 2, {"last_assistant_message": "Done with part one.\n\nShould I rename the module?"})
    expect("question in bold", 2, {"last_assistant_message": "Notes.\n\n**Do you want me to continue?**"})
    expect("options listed", 2, {"last_assistant_message": "Two ways.\n\nWhich one do you prefer:\n- A: keep it\n- B: drop it"})
    expect("option lines", 2, {"last_assistant_message": "Pick one.\n\nOption A: keep it\nOption B: drop it"})
    expect("list after a lead-in paragraph", 2, {"last_assistant_message": "Choose how to go on.\n\n1. keep it\n2. drop it"})
    expect("parked", 2, {"last_assistant_message": "Finished. I will ask the open questions later."})
    expect("waiting on decision", 2, {"last_assistant_message": "Waiting on your decision for the schema."})
    expect("AskUserQuestion used", 0, {"last_assistant_message": "Should I rename the module?",
                                       "transcript_path": transcript(tmp, ask=True)})
    expect("no ask in transcript still blocks", 2, {"last_assistant_message": "Should I rename the module?",
                                                    "transcript_path": transcript(tmp)})
    expect("stop_hook_active", 0, {"last_assistant_message": "Should I rename it?", "stop_hook_active": True})
    expect("code block question", 0, {"last_assistant_message": "Added the check.\n\n```\nprint('what now, you?')  # really?\n```\n\nDone."})
    expect("question only in code block at end", 0, {"last_assistant_message": "Result:\n\n```\nDo you agree?\n```"})
    expect("quoted question", 0, {"last_assistant_message": "The log said:\n\n> Do you want to continue?"})
    expect("inline code", 0, {"last_assistant_message": "The flag `--yes` answers \"do you want to go on?\". Done."})
    expect("plain statement", 0, {"last_assistant_message": "All done. Tests pass."})
    expect("rhetorical not addressed", 0, {"last_assistant_message": "The cache was stale. Why did it fail?"})
    expect("empty input", 0, {})
    p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    if p.returncode != 0:
        errors.append("bad JSON must fail open")

    # Q-5: parking is allowed while agents run.
    proj = Path(tempfile.mkdtemp())
    (proj / ".delivery").mkdir()
    ledger = proj / ".delivery" / "ledger.json"
    msg = {"last_assistant_message": "Parked: I will ask later.", "cwd": str(proj)}
    ledger.write_text(json.dumps({"agents": [{"state": "running"}]}))
    expect("parked, agents running", 0, msg)
    ledger.write_text(json.dumps({"agents": [{"state": "done"}]}))
    expect("parked, agents done", 2, msg)
    ledger.write_text(json.dumps({"agents": [{"state": "running"}]}))
    expect("plain question, agents running", 2, {"last_assistant_message": "Should I go on?", "cwd": str(proj)})

    # switches
    q = {"last_assistant_message": "Should I rename it?"}
    expect("env off", 0, q, env={"CLAUDE_QUESTIONS_STOP": "off"})
    home = tempfile.mkdtemp()
    (Path(home) / ".claude").mkdir()
    (Path(home) / ".claude/settings.json").write_text(json.dumps({"questionsStop": "off"}))
    expect("settings key off", 0, q, home=home)
    (Path(home) / ".claude/settings.json").write_text(json.dumps({"env": {"CLAUDE_QUESTIONS_STOP": "off"}}))
    expect("settings env off", 0, q, home=home)

    # wiring
    settings = json.loads((SKILL / "assets/.claude/settings.json").read_text())
    stop = json.dumps(settings.get("hooks", {}).get("Stop", []))
    if "questions_stop.py" not in stop:
        errors.append("settings template has no Stop hook for questions_stop.py")
    skill = (SKILL / "SKILL.md").read_text()
    for need in ("questions_stop.py", "CLAUDE_QUESTIONS_STOP", "hooks.Stop"):
        if need not in skill:
            errors.append(f"SKILL.md lacks {need}")
    for rule in (SKILL / "assets/.claude/rules/clarifying-questions.md",
                 ROOT / "claude/plugins/delivery/rules/clarifying-questions.md"):
        if "questions_stop.py" not in rule.read_text():
            errors.append(f"{rule.name} does not point Q-1/Q-2 at the hook")

    for e in errors:
        print("FAIL:", e)
    print(f"questions_stop: {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
