"""Opt-in shared component templates (DOCSPEC R15.10): design_system.py components."""
import re
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


if __name__ == "__main__":
    unittest.main()
