"""DL146: mock_handler_guard.py fails when an added client API function has no default e2e mock handler."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent / "templates" / "ts" / "scripts" / "delivery" / "mock_handler_guard.py")

CLIENT = "export async function listItems() {\n  return fetch('/api/items');\n}\n"
NEW_FN = "\nexport async function createWidget(body: unknown) {\n  return fetch(`/api/widgets/${body}`, { method: 'POST' });\n}\n"
MOCK = "import { http } from 'msw';\nexport const handlers = [\n  http.get('/api/items', () => null),\n];\n"
MOCK_WIDGET = MOCK.replace("];", "  http.post('/api/widgets/:id', () => null),\n];")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run(root):
    return subprocess.run([sys.executable, str(SCRIPT), "--base-ref", "base", "--root", str(root)],
                          capture_output=True, text=True)


class Guard(unittest.TestCase):
    def repo(self, client=CLIENT, mock=MOCK, cfg=None, client_path="apps/web/src/api/client.ts",
             mock_path="apps/web/src/mocks/handlers.ts"):
        root = tempfile.mkdtemp(prefix="dl146-")
        git(root, "init", "-q", "-b", "main")
        if client is not None:
            write(root, client_path, client)
        if mock is not None:
            write(root, mock_path, mock)
        if cfg is not None:
            write(root, ".delivery/config.json", json.dumps(cfg))
        write(root, "README.md", "x")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "base")
        git(root, "branch", "base")
        git(root, "checkout", "-q", "-b", "task")
        return root

    def commit(self, root, rel, text):
        write(root, rel, text)
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "change")

    def test_added_function_with_handler_passes(self):
        root = self.repo()
        self.commit(root, "apps/web/src/api/client.ts", CLIENT + NEW_FN)
        self.commit(root, "apps/web/src/mocks/handlers.ts", MOCK_WIDGET)
        done = run(root)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_added_function_without_handler_fails_with_message(self):
        root = self.repo()
        self.commit(root, "apps/web/src/api/client.ts", CLIENT + NEW_FN)
        done = run(root)
        self.assertEqual(done.returncode, 1)
        self.assertIn("/api/widgets/${body}", done.stderr)
        self.assertIn("POST", done.stderr)
        self.assertIn("createWidget", done.stderr)
        self.assertIn("apps/web/src/mocks/handlers.ts", done.stderr)

    def test_unchanged_client_passes_even_if_old_route_has_no_handler(self):
        root = self.repo(client=CLIENT + NEW_FN)
        self.commit(root, "README.md", "y")
        self.assertEqual(run(root).returncode, 0)

    def test_no_config_and_no_files_passes_with_note(self):
        root = self.repo(client=None, mock=None)
        done = run(root)
        self.assertEqual(done.returncode, 0)
        self.assertIn("no API client or no shared e2e mock", done.stdout)

    def test_configured_paths_work(self):
        cfg = {"e2e_mock": {"client": ["src/rest.ts"], "mock": ["test/fake/*.ts"]}}
        root = self.repo(client=CLIENT, mock=MOCK, cfg=cfg, client_path="src/rest.ts", mock_path="test/fake/h.ts")
        self.commit(root, "src/rest.ts", CLIENT + NEW_FN)
        done = run(root)
        self.assertEqual(done.returncode, 1)
        self.assertIn("test/fake/h.ts", done.stderr)
        self.commit(root, "test/fake/h.ts", MOCK_WIDGET)
        self.assertEqual(run(root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
