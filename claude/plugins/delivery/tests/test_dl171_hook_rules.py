"""DL171: DL-42 per segment, the record folder (DL-63 retired, DS303), Q-2 false positives."""
import json
import unittest
from datetime import timedelta
from pathlib import Path

from _helpers import make_root
import hook_pre_tool as P
import hook_stop as S
import hooklib as H


def kill(cmd):
    try:
        for seg in H.segments(cmd):
            P.check_kill(seg, cmd)
    except P.Deny as d:
        return str(d)
    return None


class Dl42(unittest.TestCase):
    def test_lookup_inside_exec_is_allowed(self):
        for c in ("docker exec $(docker ps -q --filter name=pool | head -1) sh -c 'gcc --version'",
                  "docker logs $(docker ps -q --filter name=pool | head -1)",
                  "docker inspect $(docker container ls -q)",
                  "docker cp $(docker ps -q | head -1):/a /b"):
            self.assertIsNone(kill(c), c)

    def test_true_positives_stay(self):
        for c in ("pkill node", "taskkill /F /IM node.exe", "killall python", "docker stop $(docker ps -q)",
                  "docker rm -f $(docker container ls -q)", "docker compose down $(docker ps -q)",
                  "docker ps -q | xargs docker stop", "kill $(pgrep node)", "Stop-Process $(docker ps -q)"):
            self.assertIn("DL-42", kill(c) or "", c)

    def test_named_stop_is_fine(self):
        self.assertIsNone(kill("docker stop abc123"))
        self.assertIsNone(kill("docker ps -q | head -1"))


class Dl63(unittest.TestCase):
    def rows(self, root, rel):
        d = Path(root) / rel
        d.mkdir(parents=True)
        (d / "registry.json").write_text(json.dumps({"tasks": [
            {"id": "T1", "item": "x", "status": "Running", "expected": "4 Nov 10:00"}]}))

    def test_default_record_dir(self):
        root = make_root()
        self.assertEqual(H.record_dir(str(root)), "docs/project")

    def test_docs_json_then_artifacts_json(self):
        root = make_root()
        (root / "docs").mkdir()
        (root / ".claude").mkdir()
        (root / ".claude" / "artifacts.json").write_text(json.dumps({"record_dir": "rec/a"}))
        self.assertEqual(H.record_dir(str(root)), "rec/a")
        (root / "docs" / "docs.json").write_text(json.dumps({"record_dir": "rec/d"}))
        self.assertEqual(H.record_dir(str(root)), "rec/d")

    def test_past_expected_is_left_to_the_docs_plugin(self):
        # DS303: DL-63 is merged into ARTIFACTSPEC R8.19; the delivery Stop hook no longer reads Expected times
        root = make_root()
        self.rows(root, "docs/project")
        self.assertFalse(hasattr(S, "check_registry"))
        out = S.findings(str(root), {}, H.load_config(str(root)))
        self.assertFalse(any(k.startswith("DL-63") for k, _ in out), out)


class Q2(unittest.TestCase):
    def test_real_question_list_blocks(self):
        t = "Open points:\n\n1. Which name do you want?\n2. Should I keep the flag?\n"
        self.assertEqual(len(S.check_questions_text(t)), 1)

    def test_code_span_quote_and_closer_do_not_count(self):
        for t in ("Done:\n\n- ran `what now?` ok\n- the log said \"why?\" once\n",
                  "Done:\n\n- fixed it\n- passes\n\n> Is this fine?\n",
                  "Notes:\n\n1. Is it done? yes\n2. Is it safe? yes\n\nNo question for you.",
                  "Notes:\n\n- changed the hook\n- added tests\n\nNo questions for you."):
            if "Is it done" in t:
                self.assertEqual(S.trailing_questions(t.replace("Is it done? yes", "x").replace("Is it safe? yes", "y")), [])
            else:
                self.assertEqual(S.check_questions_text(t), [], t)

    def test_closing_line_does_not_hide_real_list(self):
        t = "Pick:\n\n1. Which name?\n2. Which flag?\n\nNo question for you on the rest."
        self.assertEqual(len(S.check_questions_text(t)), 1)


if __name__ == "__main__":
    unittest.main()
