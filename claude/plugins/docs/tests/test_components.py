"""Opt-in shared component templates (DOCSPEC R15.10): design_system.py components."""
import re
from pathlib import Path
import unittest

from _helpers import *  # noqa
import design_system as S

SRC = S.TEMPLATES / "components" / "react-typescript"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def ds_repo():
    d = project()
    assert S.cmd_init(d, True) == 0
    return d


def spec(d):
    return (d / "docs/design-system/next-version/components.md").read_text(encoding="utf-8")


class ComponentTemplateTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        d = ds_repo()
        before = spec(d)
        self.assertEqual(S.main(["components", "--root", str(d)]), 0)
        self.assertFalse((d / S.COMPONENT_DEST).exists())
        self.assertEqual(spec(d), before)

    def test_apply_copies_code_and_adds_numbered_sections_once(self):
        d = ds_repo()
        last = max(int(x) for x in S.SECTION_NUM_RE.findall(spec(d)))
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        for name, (_title, files) in S.COMPONENTS.items():
            for f in files + S.COMPONENT_SHARED:
                self.assertTrue((d / S.COMPONENT_DEST / f).is_file(), f)
        text = spec(d)
        for i, title in enumerate(("Date picker", "Time picker", "Number keypad"), start=1):
            self.assertIn(f"## {last + i}. {title}", text)
        self.assertNotIn("{{", text)
        self.assertIn(f"`{S.COMPONENT_DEST}/DatePicker.tsx`", text)
        self.assertLess(text.index("Number keypad"), text.index("## How to add a component"))
        changes = (d / "docs/design-system/next-version/CHANGES.md").read_text(encoding="utf-8")
        self.assertEqual(changes.count("luismc-docs component templates"), 1)
        # a second run changes nothing
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        self.assertEqual(spec(d), text)
        self.assertEqual((d / "docs/design-system/next-version/CHANGES.md").read_text(encoding="utf-8"), changes)

    def test_only_one_component_and_a_custom_dest(self):
        d = ds_repo()
        self.assertEqual(S.main(["components", "--root", str(d), "--only", "time-picker", "--dest", "packages/ui/src", "--apply"]), 0)
        dest = d / "packages/ui/src"
        self.assertTrue((dest / "TimePicker.tsx").is_file())
        self.assertTrue((dest / "PickerIcon.tsx").is_file())
        self.assertFalse((dest / "DatePicker.tsx").exists())
        self.assertIn("Time picker", spec(d))
        self.assertNotIn("Number keypad", spec(d))
        self.assertIn("`packages/ui/src/TimePicker.tsx`", spec(d))

    def test_refuses_unknown_component_and_stack(self):
        d = ds_repo()
        self.assertEqual(S.main(["components", "--root", str(d), "--only", "colour-wheel"]), 2)
        self.assertEqual(S.main(["components", "--root", str(d), "--stack", "typescript-vitest"]), 2)
        self.assertEqual(S.main(["guards", "--root", str(d), "--stack", "react-typescript"]), 2)

    def test_never_overwrites_a_project_file(self):
        d = ds_repo()
        w(d, f"{S.COMPONENT_DEST}/DatePicker.tsx", "// mine\n")
        S.main(["components", "--root", str(d), "--apply"])
        self.assertEqual((d / S.COMPONENT_DEST / "DatePicker.tsx").read_text(), "// mine\n")

    def test_without_a_design_system_it_copies_code_only(self):
        d = project()
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        self.assertTrue((d / S.COMPONENT_DEST / "NumberKeypad.tsx").is_file())
        self.assertFalse((d / "docs/design-system").exists())

    def test_init_does_not_copy_the_component_templates(self):
        d = ds_repo()
        self.assertFalse((d / "docs/design-system/components").exists())

    def test_insert_is_pure_and_numbers_after_the_last_section(self):
        text = "# C\n\n## 1. A\n\n## 2. B\n"
        out, n = S.components_insert(text, "date-picker", "## {{N}}. Date picker\n- **Source:** `{{SOURCE}}/x`\n", "src/ui")
        self.assertEqual(n, 3)
        self.assertTrue(out.endswith("## 3. Date picker\n- **Source:** `src/ui/x`\n"))
        self.assertEqual(S.components_insert(out, "date-picker", "x", "y"), (out, None))

    def test_templates_use_tokens_only(self):
        tokens = (S.TEMPLATES / "next-version" / "tokens.md").read_text(encoding="utf-8")
        for p in SRC.iterdir():
            if p.suffix not in (".css", ".tsx", ".ts"):
                continue
            t = p.read_text(encoding="utf-8")
            self.assertIsNone(HEX.search(t), f"{p.name}: raw hex colour")
            self.assertNotRegex(t, r"\brgba?\(|\bhsla?\(", f"{p.name}: raw colour function")
            for var in set(re.findall(r"var\((--ds-[a-z0-9-]+)\)", t)):
                self.assertIn(f"`{var}`", tokens, f"{p.name}: {var} is not a starter token")
            if p.suffix == ".css":
                self.assertNotRegex(t, r":\s*-?\d+(\.\d+)?(px|rem|em)\b", f"{p.name}: raw size")

    def test_touch_target_and_focus_ring(self):
        base = (SRC / "picker-base.css").read_text(encoding="utf-8")
        self.assertIn("min-block-size: var(--ds-target-min)", base)
        self.assertIn("min-inline-size: var(--ds-target-min)", base)
        self.assertIn(":focus-visible", base)
        self.assertIn("var(--ds-color-focus)", base)

    def test_every_listed_file_exists_and_every_component_has_a_spec_block(self):
        for name, (_t, files) in S.COMPONENTS.items():
            for f in files:
                self.assertTrue((SRC / f).is_file(), f)
            block = (SRC / "spec" / f"{name}.md").read_text(encoding="utf-8")
            for line in ("**Used for:**", "**Looks:**", "**Source:**", "**Rules:**", "**Guard:**"):
                self.assertIn(line, block, f"{name}: {line}")
            self.assertTrue(block.startswith("## {{N}}. "), name)
        for f in S.COMPONENT_SHARED:
            self.assertTrue((SRC / f).is_file(), f)

    def test_spec_sections_cite_ux56(self):
        rules = (S.TEMPLATES / "next-version" / "ux-rules.md").read_text(encoding="utf-8")
        self.assertRegex(rules, r"(?m)^\| UX-56 \| \*\*Dates use the date picker, times use the time picker")
        for name in S.COMPONENTS:
            block = (SRC / "spec" / f"{name}.md").read_text(encoding="utf-8")
            rules_line = next(x for x in block.splitlines() if x.startswith("- **Rules:**"))
            self.assertIn("UX-56", rules_line, name)
            self.assertIn("raw-inputs.test.ts", block, name)


class ComponentWordsTests(unittest.TestCase):
    def content(self, d):
        return (d / "docs/design-system/next-version/content.md").read_text(encoding="utf-8")

    def test_words_of_each_spec_block_are_read(self):
        for name in S.COMPONENTS:
            words = S.component_words((SRC / "spec" / f"{name}.md").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(words), 5, name)
        self.assertIn("Previous month", S.component_words((SRC / "spec/date-picker.md").read_text(encoding="utf-8")))

    def test_apply_appends_words_once_with_no_duplicates(self):
        d = ds_repo()
        before = self.content(d)
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        text = self.content(d)
        self.assertTrue(text.startswith(before.rstrip("\n")))  # appended, nothing above changed
        self.assertEqual(text.count(S.WORDS_HEAD), 1)
        self.assertIn("| Previous month | Date picker |", text)
        self.assertIn("| More {unit} | Time picker |", text)
        self.assertIn("| Delete last digit | Number keypad |", text)
        # Clear, Cancel and Done are already in the action vocabulary: no second row
        for w in ("Clear", "Cancel", "Done"):
            row = r"^\| " + w + r" \|"
            self.assertEqual(len(re.findall(row, text, re.M)), len(re.findall(row, before, re.M)), w)
        table = text.split(S.WORDS_HEAD)[1]
        rows = re.findall(r"^\| ([^|]+?) \|", table, re.M)
        self.assertEqual(len(rows), len(set(rows)))
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        self.assertEqual(self.content(d), text)

    def test_a_later_component_adds_rows_to_the_same_table(self):
        d = ds_repo()
        self.assertEqual(S.main(["components", "--root", str(d), "--only", "date-picker", "--apply"]), 0)
        (d / "docs/design-system/next-version/content.md").write_text(
            self.content(d) + "\n## Project words\n\n| Word | Meaning |\n|---|---|\n| Hours | kept by the project |\n", encoding="utf-8")
        self.assertEqual(S.main(["components", "--root", str(d), "--only", "time-picker", "--apply"]), 0)
        text = self.content(d)
        self.assertEqual(text.count(S.WORDS_HEAD), 1)
        table = text.split(S.WORDS_HEAD)[1].split("## Project words")[0]
        self.assertIn("| Minutes | Time picker |", table)
        self.assertNotIn("| Hours | Time picker |", text)  # already in a table of the file
        self.assertIn("| Hours | kept by the project |", text.split("## Project words")[1])

    def test_dry_run_leaves_content_alone(self):
        d = ds_repo()
        before = self.content(d)
        self.assertEqual(S.main(["components", "--root", str(d)]), 0)
        self.assertEqual(self.content(d), before)

    def test_content_words_add_is_pure_and_idempotent(self):
        text, got = S.content_words_add("# Content\n", "X", ["A", "B", "A"])
        self.assertEqual(got, ["A", "B"])
        self.assertEqual(S.content_words_add(text, "X", ["A", "B"]), (text, []))


class ComponentGalleryTests(unittest.TestCase):
    def test_the_three_components_are_drawn(self):
        import gallery_draw as GD
        import gallery_tokens as GT
        for title in ("date picker", "time picker", "number keypad"):
            self.assertIn(title, GD.DRAWINGS)
        d = ds_repo()
        self.assertEqual(S.main(["components", "--root", str(d), "--apply"]), 0)
        html = (d / "docs/design-system/next-version/review-visuals/index.html").read_text(encoding="utf-8")
        not_drawn = html.split("Not drawn")[1].split("</section>")[0]
        for title in ("Date picker", "Time picker", "Number keypad"):
            self.assertNotIn(title, not_drawn)
        self.assertIn("every component section has a drawing", not_drawn)
        self.assertEqual(html.count('class="cr fail"'), 0)
        tokens = GT.Tokens((S.TEMPLATES / "next-version" / "tokens.md").read_text(encoding="utf-8"))
        tp = GD.d_time_picker(GD.Draw(tokens))
        for unit in ("(h)", "(hm)", "(hms)", "Seconds"):
            self.assertIn(unit, tp)
        for fn in (GD.d_date_picker, GD.d_time_picker, GD.d_number_keypad):
            draw = GD.Draw(tokens)
            fn(draw)
            self.assertEqual(draw.missing, [], fn.__name__)  # every token it reads is in the starter
        self.assertIn(">31<", GD.d_date_picker(GD.Draw(tokens)))


class RawInputsGuardTests(unittest.TestCase):
    """The raw-inputs guard template (UX-56) runs under the Node vitest shim when Node 22.6+ is there."""
    KIT = S.TEMPLATES / "guards" / "typescript-vitest-kit"
    SHIM = Path(__file__).resolve().parents[4] / "tools" / "fixtures" / "vitest_shim" / "run.mjs"

    def node_ok(self):
        import shutil
        import subprocess
        if not shutil.which("node") or not self.SHIM.is_file():
            return False
        out = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout
        m = re.match(r"v(\d+)\.(\d+)", out)
        return bool(m) and (int(m.group(1)), int(m.group(2))) >= (22, 6)

    def test_files_and_empty_allowlist(self):
        import json
        for n in ("raw-inputs-scan.ts", "raw-inputs.test.ts", "raw-inputs.known.json"):
            self.assertTrue((self.KIT / n).is_file(), n)
        data = json.loads((self.KIT / "raw-inputs.known.json").read_text(encoding="utf-8"))
        self.assertEqual(data["entries"], [])
        scan = (self.KIT / "raw-inputs-scan.ts").read_text(encoding="utf-8")
        for t in ("'date'", "'time'", "'datetime-local'", "'number'"):
            self.assertIn(t, scan)

    def _run(self, files: dict, known: list):
        import json
        import shutil
        import subprocess
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="raw-inputs-"))
        try:
            dest = d / "scripts" / "design"
            shutil.copytree(self.KIT, dest)
            (dest / "raw-inputs.known.json").write_text(json.dumps({"entries": known}), encoding="utf-8")
            for rel, text in files.items():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text(text, encoding="utf-8")
            return subprocess.run(["node", str(self.SHIM), "raw-inputs.test.ts"], cwd=dest,
                                  capture_output=True, text=True, timeout=120)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_guard_catches_each_banned_type_and_honours_the_allowlist(self):
        if not self.node_ok():
            self.skipTest("Node 22.6 or later not found")
        clean = self._run({"apps/web/a.tsx": '<input type="text" />'}, [])
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn(" 0 failed", clean.stdout)
        for t in ("date", "time", "datetime-local", "number"):
            src = {"apps/web/src/a.tsx": f'<input type="{t}" />'}
            bad = self._run(src, [])
            self.assertNotEqual(bad.returncode, 0, t)
            self.assertIn("apps/web/src/a.tsx: 1 new type=", bad.stdout + bad.stderr, t)
            self.assertIn(t, bad.stdout.split("1 new type=")[1][:20], t)
            ok = self._run(src, [{"file": "apps/web/src/a.tsx", "type": t, "count": 1}])
            self.assertEqual(ok.returncode, 0, t + ok.stdout + ok.stderr)
        # a listed breach that is gone fails: the allowlist only shrinks
        stale = self._run({"apps/web/src/a.tsx": "<DatePicker />"}, [{"file": "apps/web/src/a.tsx", "type": "date", "count": 1}])
        self.assertNotEqual(stale.returncode, 0)
        # a test file is not judged
        tests = self._run({"apps/web/src/a.test.tsx": '<input type="date" />'}, [])
        self.assertEqual(tests.returncode, 0, tests.stdout)


if __name__ == "__main__":
    unittest.main()
