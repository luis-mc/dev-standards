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
            if 'apt-get install' in r and 'clang-${LLVM_VERSION}' in r:
                return i, r
        self.fail('no apt install of clang-${LLVM_VERSION}')

    def test_version_pinned_once_at_19_or_newer(self):
        """DL170: the MSVC CRT needs Clang >= 19; one ARG sets the version."""
        m = re.findall(r'^ARG LLVM_VERSION=(\d+)$', DF.read_text(encoding='utf-8'), re.M)
        self.assertEqual(len(m), 1)
        self.assertGreaterEqual(int(m[0]), 19)

    def test_packages_in_always_on_layer(self):
        _, r = self.install_index()
        for pkg in ('clang', 'lld', 'llvm'):
            self.assertIn('"%s-${LLVM_VERSION}"' % pkg, r)
        self.assertNotIn('POOL_LAYERS', r)
        self.assertIn('--no-install-recommends', r)
        self.assertIn('rm -rf /var/lib/apt/lists/*', r)

    def test_every_tool_linked_from_the_pinned_version(self):
        _, r = self.install_index()
        self.assertIn('llvmdir="/usr/lib/llvm-${LLVM_VERSION}"', r)
        self.assertIn('ln -sf "$llvmdir/bin/clang" /usr/local/bin/clang-cl', r)
        for tool in ('clang', 'lld-link', 'llvm-lib', 'llvm-ar', 'llvm-rc', 'lld'):
            self.assertRegex(r, r'for t in [^;]*\b%s\b' % re.escape(tool))
        self.assertIn('ln -sf "$llvmdir/bin/$t" "/usr/local/bin/$t"', r)
        self.assertIsNone(re.search(r'llvm-\d', r), 'no literal LLVM version outside the ARG')
        self.assertNotIn('command -v "$t"', r, 'never keep an older tool already on PATH')

    def test_self_check_after_install_checks_version(self):
        i, _ = self.install_index()
        later = [r for r in runs()[i + 1:] if 'clang-cl --version' in r]
        self.assertTrue(later, 'self-check must follow the install')
        for cmd in ('clang-cl --version', 'lld-link --version', 'llvm-lib'):
            self.assertIn(cmd, later[0])
        self.assertIn('-ge "$LLVM_VERSION"', later[0])

    def test_names_dl167_dl169_dl170(self):
        text = DF.read_text(encoding='utf-8')
        for tag in ('DL167', 'DL169', 'DL170'):
            self.assertIn(tag, text)


if __name__ == '__main__':
    unittest.main()
