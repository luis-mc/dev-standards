"""AR69: a lighter Full Progress page (R5.9 window, R6.3 one line, no per-cell data-label)."""
import json
import os
import re
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "claude" / "plugins" / "docs" / "scripts"))
import render_artifacts as R  # noqa: E402
import test_render_artifacts as T  # noqa: E402

OLD = "2026-05-01T10:00+01:00"
RECENT = "2026-10-05T10:00+01:00"


def big_registry(live_old=270, live_recent=6):
    tasks = [T.task("ZA%d" % i, "artifacts", "Live", "Old item %d" % i, "01 May", OLD, "luismc-docs")
             for i in range(1, live_old + 1)]
    tasks += [T.task("ZB%d" % i, "artifacts", "Live", "Recent item %d" % i, "05 Oct", RECENT, "luismc-docs")
              for i in range(1, live_recent + 1)]
    tasks += [T.task("ZD1", "artifacts", "Dropped", "Old dropped", "01 May", OLD, "luismc-docs"),
              T.task("ZD2", "artifacts", "Dropped", "Recent dropped", "05 Oct", RECENT, "luismc-docs"),
              T.task("ZR1", "artifacts", "Running", "Open work", "10 Oct ~15:30", "2026-10-10T12:00+01:00", "luismc-docs"),
              T.task("ZR2", "artifacts", "Built", "Old built", "01 May", OLD, "luismc-docs"),
              T.task("ZR3", "artifacts", "To do", "Waiting work", "12 Oct", OLD, "luismc-docs")]
    return {"spec": R.SPEC, "updated": T.STAMP_ISO, "tasks": tasks}


class LighterFullProgress(unittest.TestCase):
    def setUp(self):
        self.fx = T.Fixture()
        self.addCleanup(self.fx.close)
        self.reg = big_registry()
        self.out = self.fx.render("full-progress", registry=self.reg)

    def embedded(self):
        dom = R.parse_dom(self.out)
        script = R.find(dom, "script", pred=lambda n: n.attrs.get("type") == "application/json")
        return "".join(c.text for c in script.children)

    def test_registry_window_is_minified_and_counted(self):
        raw = self.embedded()
        self.assertNotIn("\n", raw)
        data = json.loads(raw)
        ids = {t["id"] for t in data["tasks"]}
        self.assertEqual(ids, {"ZB%d" % i for i in range(1, 7)} | {"ZD2", "ZR1", "ZR2", "ZR3"})
        self.assertEqual(data["omitted"], 270 + 1)
        self.assertEqual(data["full_registry"], R.registry_path_of(self.fx.record))
        self.assertEqual(R.registry_path_of("/x/docs/project"), "docs/project/registry.json")
        self.assertEqual(data["spec"], R.SPEC)
        self.assertEqual(self.fx.check(self.out, "full-progress", registry=self.reg), [])

    def test_no_row_for_old_live_and_one_count_line(self):
        self.assertNotIn('data-task="ZA1"', self.out)
        self.assertNotIn('data-task="ZA270"', self.out)
        self.assertIn('data-task="ZB1"', self.out)
        self.assertIn('data-task="ZR2"', self.out)        # Built is never left out
        self.assertNotIn('<details class="earlier"', self.out)
        self.assertEqual(self.out.count('class="earlier-note"'), 1)
        self.assertIn("270 earlier Live tasks (over 14 days old) are not shown; the full list is in "
                      + R.registry_path_of(self.fx.record), self.out)
        self.assertIn("1 built, 8 live, 270 earlier", self.out)

    def test_no_data_label_in_rows_and_css_names_each_column(self):
        for m in re.finditer(r'<table class="status-checklist[^"]*">.*?</table>', self.out, re.S):
            self.assertNotIn("data-label", m.group(0))
        css = R.structure_css()
        for label in ("App / service", "Detail", "Expected", "Last updated", "Tasks", "State", "Where it stands"):
            self.assertIn('content: "%s"' % label, css)

    def test_size_is_well_below_the_old_render(self):
        old_rows = "".join('<tr data-task="%s"><td data-label="Status">x</td></tr>' % t["id"] for t in self.reg["tasks"])
        full_json = json.dumps(self.reg, indent=1, ensure_ascii=False)
        old_size = len(self.out.encode()) + len(old_rows.encode()) + len(full_json.encode())
        new_size = len(self.out.encode())
        print("\nAR69 sizes: old-shape estimate %d bytes, new %d bytes" % (old_size, new_size))
        self.assertLess(new_size, old_size * 0.8)
        # the registry window is far smaller than the full registry, minified or not
        self.assertLess(len(self.embedded()), len(full_json) // 5)

    def test_checker_flags_a_full_registry(self):
        full = dict(self.reg, full_registry="docs/project/registry.json", omitted=0)
        text = json.dumps(full, separators=(",", ":"))
        bad = re.sub(r'(<script type="application/json" id="task-registry">).*?(</script>)',
                     lambda m: m.group(1) + text + m.group(2), self.out, flags=re.S)
        self.assertIn("R5.9", T.reqs(self.fx.check(bad, "full-progress", registry=self.reg)))


if __name__ == "__main__":
    unittest.main()
