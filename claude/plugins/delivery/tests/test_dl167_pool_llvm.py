"""DL167: the pool Dockerfile installs the LLVM tools for Windows builds. Reads the file; no Docker."""
import re
import unittest
from pathlib import Path

DF = Path(__file__).resolve().parents[1] / 'templates' / 'runner-pool' / 'Dockerfile'


def runs():
    text = DF.read_text(encoding='utf-8').replace('\\\n', ' ')
    return [ln for ln in text.splitlines() if ln.startswith('RUN ')]


class PoolLlvm(unittest.TestCase):
    def install_index(self):
        for i, r in enumerate(runs()):
            if 'apt-get install' in r and re.search(r'\bclang\b', r):
                return i, r
        self.fail('no apt install of clang')

    def test_packages_in_always_on_layer(self):
        _, r = self.install_index()
        for pkg in ('clang', 'lld', 'llvm'):
            self.assertRegex(r, r'\b%s\b' % pkg)
        self.assertNotIn('POOL_LAYERS', r)
        self.assertNotIn('if [', r.split('apt-get install')[0])
        self.assertIn('--no-install-recommends', r)
        self.assertIn('rm -rf /var/lib/apt/lists/*', r)

    def test_links_use_build_time_version(self):
        _, r = self.install_index()
        for t in ('clang-cl', 'lld-link', 'llvm-lib', 'llvm-ar', 'llvm-rc', 'lld'):
            self.assertIn(t, r)
        self.assertIn('/usr/local/bin', r)
        self.assertIn('ls -d /usr/lib/llvm-*', r)
        self.assertIsNone(re.search(r'llvm-\d', r), 'no literal LLVM version')
        self.assertIsNone(re.search(r'clang-cl-\d', r))

    def test_self_check_after_install(self):
        i, _ = self.install_index()
        later = [r for r in runs()[i + 1:] if 'clang-cl --version' in r]
        self.assertTrue(later, 'self-check must follow the install')
        for cmd in ('clang-cl --version', 'lld-link --version', 'llvm-lib'):
            self.assertIn(cmd, later[0])

    def test_names_dl167(self):
        self.assertIn('DL167', DF.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
