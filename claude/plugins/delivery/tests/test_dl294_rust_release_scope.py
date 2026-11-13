"""DL294: ci_scope.py returns `rust-release` for a Rust-only release pull request."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"))
import ci_scope as S  # noqa: E402

RUST = {"why": "release PR, Rust-only: Node suites skipped",
        "rust_only": ["crates", "Cargo.toml", "Cargo.lock", "rust-toolchain*", ".cargo", "deny.toml", "rustfmt.toml",
                      "packaging/linux", "vendor"],
        "node_inputs": ["apps", "packages", "scripts", "infra", "pnpm-lock.yaml", "pnpm-workspace.yaml",
                        "package.json", "tsconfig*.json", "turbo.json", "turbo.jsonc", "vitest.config.ts",
                        "playwright.config.ts", ".nvmrc", ".github"]}
CFG = {"default_branch": "main", "release_pr": {"base": "main", "head_re": "^release/.+"},
       "full_files": ["pnpm-lock.yaml", "package.json", ".github", "!.github/workflows"],
       "ci_files": ["scripts/delivery", ".github/workflows"], "docs": ["docs", "**/*.md"],
       "rust_release": RUST}


def rel(files, cfg=CFG):
    return S.decide(cfg, files, "pull_request", "release/1", "main")["scope"]


class RustReleaseScope(unittest.TestCase):
    def test_rust_only_sets(self):
        for files in (["crates/a/src/lib.rs", "Cargo.toml"],
                      ["crates/a/lib.rs", "Cargo.lock", "docs/x.md"],
                      ["Cargo.lock"],
                      ["vendor/x/y.rs", "packaging/linux/a.spec", "deny.toml", "rust-toolchain.toml"]):
            self.assertEqual(rel(files), "rust-release", files)

    def test_why_text(self):
        self.assertEqual(S.decide(CFG, ["Cargo.lock"], "pull_request", "release/1", "main")["why"], RUST["why"])

    def test_node_input_keeps_full(self):
        for f in ("apps/web/a.ts", "packages/x/a.ts", "scripts/a.js", "infra/x/package.json", "package.json"):
            self.assertEqual(rel(["crates/a/lib.rs", f]), "full", f)

    def test_full_file_forces_full(self):
        self.assertEqual(rel(["crates/a/lib.rs", "pnpm-lock.yaml"]), "full")

    def test_docs_only_release_is_full(self):
        self.assertEqual(rel(["docs/a.md"]), "full")

    def test_non_release_pr_is_affected(self):
        r = S.decide(CFG, ["crates/a/lib.rs"], "pull_request", "agent/x", "main")
        self.assertEqual(r["scope"], "affected")

    def test_no_block_is_full(self):
        cfg = {k: v for k, v in CFG.items() if k != "rust_release"}
        self.assertEqual(rel(["crates/a/lib.rs"], cfg), "full")

    def test_ci_smoke_still_first(self):
        self.assertEqual(rel(["scripts/delivery/a.py"]), "ci-smoke")


if __name__ == "__main__":
    unittest.main()
