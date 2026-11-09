"""DL147: a job that needs a skippable job must not rely on GitHub's implicit success().

A job is skippable when it has its own `if:` or needs a skippable job. A job with a skippable need
must have an `if:` that starts with `!cancelled()` (or `always()` with an explicit cancel check) and
names `needs.<name>.result` for each skippable need. Stdlib only; reads the job blocks line by line."""
import re
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _strip_comment(text):
    return re.sub(r"\s+#.*$", "", text).strip()


def read_jobs(text):
    """Return {job: {"needs": [..], "if": str or None}} for the top-level `jobs:` block."""
    lines = text.splitlines()
    jobs, cur, in_jobs, i = {}, None, False, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_jobs = line.startswith("jobs:")
            cur = None
            continue
        if not in_jobs:
            continue
        m = re.match(r"^  ([\w.-]+):\s*(#.*)?$", line)
        if indent == 2 and m:
            cur = jobs.setdefault(m.group(1), {"needs": [], "if": None})
            continue
        if cur is None or indent != 4:
            continue
        key, _, val = line.strip().partition(":")
        val = _strip_comment(val)
        if key == "needs":
            if val.startswith("["):
                cur["needs"] = [n.strip().strip("'\"") for n in val.strip("[]").split(",") if n.strip()]
            elif val:
                cur["needs"] = [val.strip("'\"")]
            else:
                while i < len(lines) and re.match(r"^\s+-\s+\S", lines[i]):
                    cur["needs"].append(_strip_comment(lines[i].strip()[1:]).strip("'\""))
                    i += 1
        elif key == "if":
            if val in (">", ">-", "|", "|-"):
                parts = []
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > 4):
                    parts.append(lines[i].strip())
                    i += 1
                val = " ".join(p for p in parts if p)
            cur["if"] = val
    return jobs


def _condition(expr):
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2].strip()
    return expr.strip("'\"").strip()


def check_text(text, label="workflow"):
    """Return a list of findings: `<label>: job '<job>' needs '<need>': <why>`."""
    jobs = read_jobs(text)
    skippable = {}

    def is_skippable(name, seen=()):
        if name not in jobs or name in seen:
            return False
        if name not in skippable:
            j = jobs[name]
            skippable[name] = j["if"] is not None or any(is_skippable(n, seen + (name,)) for n in j["needs"])
        return skippable[name]

    findings = []
    for name, job in jobs.items():
        risky = [n for n in job["needs"] if is_skippable(n)]
        if not risky:
            continue
        cond = _condition(job["if"]) if job["if"] is not None else None
        for need in risky:
            if cond is None:
                why = "no `if:`; the implicit success() skips this job when the need is skipped"
            elif not (cond.startswith("!cancelled()") or (cond.startswith("always()") and "cancelled()" in cond)):
                why = "`if:` must start with `!cancelled()` (or always() with a cancel check)"
            elif f"needs.{need}.result" not in cond:
                why = f"`if:` must check needs.{need}.result"
            else:
                continue
            findings.append(f"{label}: job '{name}' needs '{need}': {why}")
    return findings


def template_files():
    return sorted(TEMPLATES.glob("*/.github/workflows/*.yml"))


def check_all():
    out = []
    for path in template_files():
        out += check_text(path.read_text(encoding="utf-8"), str(path.relative_to(TEMPLATES)).replace("\\", "/"))
    return out


BAD_IMPLICIT = """
on: push
jobs:
  gate:
    if: ${{ github.event_name == 'push' }}
    runs-on: x
  build:
    needs: [gate]
    runs-on: x
"""
BAD_NO_STATUS = """
jobs:
  gate:
    if: ${{ github.event_name == 'push' }}
  build:
    needs: gate
    if: ${{ needs.gate.outputs.skip != 'true' }}
"""
BAD_NO_RESULT = """
jobs:
  gate:
    if: github.ref == 'x'
  build:
    needs: [gate]
    if: ${{ !cancelled() && needs.gate.outputs.skip != 'true' }}
"""
BAD_TRANSITIVE = """
jobs:
  a:
    if: github.ref == 'x'
  b:
    needs: a
    if: ${{ !cancelled() && needs.a.result == 'success' }}
  c:
    needs:
      - b
    runs-on: x
"""
GOOD = """
jobs:
  a:
    if: github.ref == 'x'
  b:
    needs: [a]
    # A skipped a is fine here; a failed one is not.
    if: ${{ !cancelled() && needs.a.result != 'failure' }}
  c:
    needs: [b]
    if: >-
      always() && !cancelled() &&
      needs.b.result == 'success'
  d:
    needs: [e]
  e:
    runs-on: x
"""


class WorkflowNeeds(unittest.TestCase):
    def test_reader_reads_needs_and_if(self):
        jobs = read_jobs(GOOD)
        self.assertEqual(jobs["b"]["needs"], ["a"])
        self.assertIn("needs.a.result", jobs["b"]["if"])
        self.assertIn("needs.b.result", jobs["c"]["if"])
        self.assertIsNone(jobs["d"]["if"])

    def test_bad_samples_name_job_and_need(self):
        for text, job, need in ((BAD_IMPLICIT, "build", "gate"), (BAD_NO_STATUS, "build", "gate"),
                                (BAD_NO_RESULT, "build", "gate"), (BAD_TRANSITIVE, "c", "b")):
            found = check_text(text, "f.yml")
            self.assertEqual(len(found), 1, found)
            self.assertIn(f"f.yml: job '{job}' needs '{need}'", found[0])

    def test_good_sample_passes(self):
        self.assertEqual(check_text(GOOD, "f.yml"), [])

    def test_templates_found(self):
        self.assertGreaterEqual(len(template_files()), 10)

    def test_every_template_workflow(self):
        found = check_all()
        self.assertEqual(found, [], "\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
