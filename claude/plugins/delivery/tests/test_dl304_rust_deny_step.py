"""DL304: the rust gate runs cargo-deny only when a manifest, the lockfile or deny.toml changed."""
import json
import sys
import unittest
from pathlib import Path

import _helpers  # noqa: F401

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(TEMPLATES / "shared" / "scripts" / "delivery"))
import delivery_common as dc  # noqa: E402
RUST_GATE = TEMPLATES / "rust" / "scripts" / "delivery" / "gate.json"


def load(path=RUST_GATE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ctx_for(cfg, files):
    return dc.Context(root=Path("."), cfg=cfg, base_ref="origin/main", base="b", head="h",
                      files=files, packages=[], changed_dirs=[], affected_dirs=[], widened=False)


def deny_step(cfg):
    return next(s for s in cfg["steps"] if s["name"] == "deny")


class RustDenyStep(unittest.TestCase):
    def plan(self, files):
        cfg = load()
        return dc.plan_step(deny_step(cfg), ctx_for(cfg, files))

    def test_order_after_lint(self):
        cfg = load()
        order = cfg["fail_fast_order"]
        self.assertEqual(order.index("deny"), order.index("lint") + 1)
        names = [s["name"] for s in cfg["steps"]]
        self.assertEqual(names.index("deny"), names.index("lint") + 1)

    def test_lockfile_runs(self):
        go, cmd, _ = self.plan(["Cargo.lock"])
        self.assertTrue(go)
        self.assertEqual(cmd, "python3 scripts/delivery/rust_ci.py deny")

    def test_member_manifest_runs(self):
        self.assertTrue(self.plan(["crates/core/Cargo.toml"])[0])

    def test_root_manifest_and_deny_toml_run(self):
        self.assertTrue(self.plan(["Cargo.toml"])[0])
        self.assertTrue(self.plan(["src/lib.rs", "deny.toml"])[0])

    def test_rs_only_skipped_with_reason(self):
        go, cmd, why = self.plan(["crates/core/src/lib.rs"])
        self.assertFalse(go)
        self.assertIsNone(cmd)
        self.assertTrue(why.startswith("no "), why)
        self.assertIn("when_changed", why)

    def test_other_tracks_unchanged(self):
        for gate in TEMPLATES.glob("*/scripts/delivery/gate.json"):
            if gate.parent.parent.parent.name == "rust":
                continue
            cfg = load(gate)
            self.assertFalse(any("when_changed" in s for s in cfg["steps"]), gate)

    def test_step_without_option_ignores_files(self):
        step = {"name": "x", "scope": "always", "run": "true"}
        cfg = load()
        self.assertTrue(dc.plan_step(step, ctx_for(cfg, ["a.rs"]))[0])

    def _root_with(self, cfg):
        import shutil
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="dl304-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "scripts" / "delivery").mkdir(parents=True)
        (root / "scripts" / "delivery" / "gate.json").write_text(json.dumps(cfg), encoding="utf-8")
        return root

    def test_shipped_gate_loads(self):
        cfg = dc.load_gate(self._root_with(load()))
        self.assertIn("when_changed", deny_step(cfg))

    def test_bad_when_changed_rejected(self):
        cfg = load()
        deny_step(cfg)["when_changed"] = []
        with self.assertRaises(dc.DeliveryError):
            dc.load_gate(self._root_with(cfg))


if __name__ == "__main__":
    unittest.main()
