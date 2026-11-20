"""DL379: every workflow job has a timeout of 30 minutes or less; artifact-prune has no workflow_run;
no pull-request job of spec-lint runs a mutation pass."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TEMPLATES = ROOT / "claude" / "plugins" / "delivery" / "templates"
FILES = sorted(TEMPLATES.glob("*/.github/workflows/*.yml")) + sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def jobs(text):
    """{job id: its text} from the top-level `jobs:` block (no YAML library)."""
    out, cur, inside = {}, None, False
    for line in text.split("\n"):
        if re.match(r"^jobs:\s*$", line):
            inside = True
            continue
        if inside and line.strip() and re.match(r"^\S", line) and not line.startswith("#"):
            inside = False
        if not inside:
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(x for x in v if not x.lstrip().startswith("#")) for k, v in out.items()}


def timeout(body):
    m = re.search(r"^    timeout-minutes:\s*(\d+)\s*$", body, re.M)
    return int(m.group(1)) if m else None


class Guardrails(unittest.TestCase):
    def test_files_found(self):
        self.assertGreaterEqual(len(FILES), 15)

    def test_every_job_has_timeout_of_30_or_less(self):
        bad = []
        for f in FILES:
            for name, body in jobs(f.read_text(encoding="utf-8")).items():
                if re.search(r"^    uses:", body, re.M):
                    continue  # a called workflow sets its own jobs' limits
                t = timeout(body)
                if t is None or t > 30:
                    bad.append(f"{f.relative_to(ROOT)}:{name}={t}")
        self.assertEqual(bad, [])

    def test_prune_has_no_workflow_run(self):
        text = (TEMPLATES / "shared/.github/workflows/artifact-prune.yml").read_text(encoding="utf-8")
        on = text.split("\non:", 1)[1].split("\njobs:", 1)[0]
        self.assertNotIn("workflow_run", on)
        self.assertIn("schedule:", on)
        self.assertIn("workflow_dispatch:", on)

    def test_no_pull_request_mutation_pass(self):
        text = (ROOT / ".github/workflows/spec-lint.yml").read_text(encoding="utf-8")
        for name, body in jobs(text).items():
            cond = re.search(r"^    if:(.*)$", body, re.M)
            cond = cond.group(1) if cond else ""
            if re.search(r"--no-scenarios|--shard", body):  # the mutation pass
                self.assertIn("!= 'pull_request'", cond, name)
            for m in re.finditer(r"run: python3 tools/test_\w+\.py ([^\n]*)", body):
                if "mutants_" in m.group(1):
                    self.assertIn("github.event_name == 'pull_request') && '--no-mutants'", m.group(1), name)


if __name__ == "__main__":
    unittest.main()
