"""DS201: static checks of the rust workflows and scope_map step selection."""
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
import delivery_common as dc  # noqa: E402

WF = BASE / "rust" / ".github" / "workflows"
CI = (WF / "ci.yml").read_text(encoding="utf-8")
PKG = (WF / "package.yml").read_text(encoding="utf-8")
TS_CI = (BASE / "ts" / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def code(text):
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


class Workflows(unittest.TestCase):
    def test_no_floating_toolchain(self):
        for text in (CI, PKG):
            self.assertNotIn("dtolnay", code(text))
            self.assertIn("rust_ci.py toolchain", text)
            self.assertIn("rust_ci.py env", text)

    def test_no_soft_installs(self):
        for text in (CI, PKG):
            self.assertNotIn("|| true", code(text))
            self.assertNotIn("cargo install --locked cargo-deny", code(text))
        self.assertIn("rust_ci.py deny", CI)

    def test_cache_only_on_hosted(self):
        for text in (CI, PKG):
            for m in re.finditer(r"- uses: Swatinem/rust-cache@\S+.*\n(.*)\n", text):
                self.assertIn("runner.environment == 'github-hosted'", m.group(1))

    def test_cancel_expression_copied(self):
        want = re.search(r"cancel-in-progress: (.*)", TS_CI).group(1)
        self.assertEqual(re.search(r"cancel-in-progress: (.*)", CI).group(1), want)

    def test_path_filter(self):
        """DS206: pull requests use a positive Rust list; push keeps paths-ignore with docs and md."""
        head = CI.split("concurrency:")[0]
        pr, push = head.split("  push:")
        paths = re.findall(r"^\s+- '([^']+)'", pr, re.M)
        for p in ("crates/**", "**/Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rustfmt.toml", "deny.toml",
                  "**/*.rs", "scripts/delivery/rust_ci.py", "tools.json"):
            self.assertIn(p, paths)
        self.assertNotIn("paths-ignore", code(pr))
        line = [ln for ln in push.splitlines() if ln.strip().startswith("paths-ignore:")]
        self.assertEqual(len(line), 1)
        self.assertIn("'docs/**'", line[0])
        self.assertIn("'**/*.md'", line[0])
        self.assertNotIn("'apps/**'", line[0])  # Rust under apps/ must still run on push
        for p in ("crates", "Cargo", "rust-toolchain", "rustfmt", "deny.toml", "scripts/delivery", "tools.json"):
            self.assertNotIn(p, line[0])

    def test_js_workflow_ignores_rust_only_paths(self):
        head = TS_CI.split("concurrency:")[0]
        blocks = re.findall(r"paths-ignore:\n((?:\s+- '[^']+'\n)+)", head)
        self.assertEqual(len(blocks), 2)
        for b in blocks:
            got = re.findall(r"'([^']+)'", b)
            for p in ("crates/**", "**/Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rustfmt.toml",
                      "deny.toml", "**/*.rs", "scripts/delivery/rust_ci.py", "docs/**", "**/*.md"):
                self.assertIn(p, got)
            self.assertNotIn("tools.json", got)  # shared with the JS side
            self.assertNotIn("apps/**", got)

    def test_filter_rules_by_changed_files(self):
        """DS206: a JS-only change skips Rust, a Rust-only change skips JS, apps/ Rust runs Rust."""
        def rx(g):
            return re.compile("^" + re.escape(g).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
                              .replace(r"\*", "[^/]*") + "$")
        pr = CI.split("concurrency:")[0].split("  push:")[0]
        rust_on = [rx(p) for p in re.findall(r"^\s+- '([^']+)'", pr, re.M)]
        ts_head = TS_CI.split("concurrency:")[0]
        block = re.search(r"paths-ignore:\n((?:\s+- '[^']+'\n)+)", ts_head).group(1)
        ts_off = [rx(p) for p in re.findall(r"'([^']+)'", block)]
        rust_runs = lambda fs: any(r.match(f) for f in fs for r in rust_on)  # noqa: E731
        ts_runs = lambda fs: not all(any(r.match(f) for r in ts_off) for f in fs)  # noqa: E731
        js = ["apps/web/src/a.ts", "packages/ui/index.ts", "pnpm-lock.yaml"]
        self.assertFalse(rust_runs(js))
        self.assertTrue(ts_runs(js))
        rs = ["crates/core/src/lib.rs", "Cargo.lock", "crates/core/Cargo.toml"]
        self.assertTrue(rust_runs(rs))
        self.assertFalse(ts_runs(rs))
        self.assertTrue(rust_runs(["apps/desktop/src-tauri/src/main.rs"]))
        self.assertFalse(ts_runs(["apps/desktop/src-tauri/src/main.rs"]))
        self.assertTrue(rust_runs(["apps/desktop/src-tauri/Cargo.toml"]))
        self.assertTrue(rust_runs(["tools.json"]) and ts_runs(["tools.json"]))
        self.assertTrue(rust_runs(rs + js) and ts_runs(rs + js))
        self.assertFalse(ts_runs(["docs/a.md"]))

    def test_artifact_names_stable(self):
        names = re.findall(r"^\s+name: (\S+)\n\s+path:", PKG, re.M)
        self.assertEqual(names, ["packaged-program", "packaged-program-windows"])
        for n in names:
            self.assertNotIn("${{", n)
        self.assertNotIn("download-artifact", PKG)
        self.assertIn("cargo xwin build", PKG)


def ctx(files, smap, widened=False):
    return SimpleNamespace(files=files, cfg={"scope_map": smap} if smap is not None else {}, widened=widened)


SMAP = {"rust": ["Cargo.toml", "crates/**"], "js": ["apps/**", "package.json"], "note": "x"}


class ScopeMap(unittest.TestCase):
    rust = {"name": "lint", "paths": "rust"}
    js = {"name": "ts", "paths": "js"}

    def test_rust_change_skips_js_step(self):
        c = ctx(["crates/a/src/lib.rs"], SMAP)
        self.assertIsNone(dc.scope_skip(self.rust, c))
        self.assertIn("js", dc.scope_skip(self.js, c))

    def test_js_change_skips_rust_step(self):
        c = ctx(["apps/web/x.ts"], SMAP)
        self.assertIn("rust", dc.scope_skip(self.rust, c))
        self.assertIsNone(dc.scope_skip(self.js, c))

    def test_mixed_and_unmapped_run_everything(self):
        for files in (["crates/a.rs", "apps/x.ts"], ["crates/a.rs", "README.md"], ["README.md"]):
            c = ctx(files, SMAP)
            self.assertIsNone(dc.scope_skip(self.rust, c))
            self.assertIsNone(dc.scope_skip(self.js, c))

    def test_no_map_no_paths_unknown_key(self):
        self.assertIsNone(dc.scope_skip(self.js, ctx(["crates/a.rs"], None)))
        self.assertIsNone(dc.scope_skip({"name": "s"}, ctx(["crates/a.rs"], SMAP)))
        self.assertIsNone(dc.scope_skip({"name": "s", "paths": "go"}, ctx(["crates/a.rs"], SMAP)))
        self.assertIsNone(dc.scope_skip(self.js, ctx([], SMAP)))

    def test_plan_step_uses_it(self):
        step = {"name": "ts", "scope": "always", "run": "x", "paths": "js"}
        c = ctx(["crates/a.rs"], SMAP)
        c.base, c.packages, c.changed_dirs, c.affected_dirs = "b", [], [], []
        run, cmd, why = dc.plan_step(step, c)
        self.assertFalse(run)
        c.files = ["apps/a.ts"]
        self.assertTrue(dc.plan_step(step, c)[0])

    def test_shipped_rust_gate_loads(self):
        import json
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "scripts" / "delivery").mkdir(parents=True)
        (d / "scripts" / "delivery" / "gate.json").write_text(
            (BASE / "rust" / "scripts" / "delivery" / "gate.json").read_text(encoding="utf-8"), encoding="utf-8")
        cfg = dc.load_gate(d)
        self.assertIn("rust", cfg["scope_map"])
        self.assertTrue(json.dumps(cfg))


if __name__ == "__main__":
    unittest.main()
