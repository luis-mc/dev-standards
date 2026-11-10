"""DL180: Wine wrappers unset TMPDIR in the pool image. Reads the Dockerfile; no Docker."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DF = Path(__file__).resolve().parents[1] / 'templates' / 'runner-pool' / 'Dockerfile'


def runs():
    text = DF.read_text(encoding='utf-8').replace('\\\n', ' ')
    return [ln for ln in text.splitlines() if ln.startswith('RUN ')]


def block_index():
    for i, r in enumerate(runs()):
        if 'DL180' in r:
            return i, r
    raise AssertionError('no DL180 RUN block')


class WineTmpdir(unittest.TestCase):
    def test_block_after_windows_packaging_install(self):
        i, _ = block_index()
        inst = [k for k, r in enumerate(runs()) if 'windows-packaging' in r and 'apt-get install' in r]
        self.assertEqual(len(inst), 1)
        self.assertGreater(i, inst[0])

    def test_guarded_by_layer(self):
        _, r = block_index()
        self.assertIn('command -v wine', r)
        self.assertIn('[ -x "/usr/bin/$t" ] || continue', r)

    def test_tools_and_target(self):
        _, r = block_index()
        loop = re.search(r'for t in ([^;]*);', r).group(1).split()
        for t in ('wine', 'wine64', 'wineboot', 'wineserver', 'msiexec'):
            self.assertIn(t, loop)
        self.assertIn('> "/usr/local/bin/$t"', r)
        self.assertIn('chmod 0755 "/usr/local/bin/$t"', r)
        self.assertIn('unset TMPDIR', r)
        self.assertIn('exec /usr/bin/%s "$@"', r)

    def test_path_self_check(self):
        _, r = block_index()
        # DL182: dash caches the path of wine after the first command -v; hash -r makes the check see the wrapper.
        self.assertIn('hash -r; [ "$(command -v wine)" = /usr/local/bin/wine ]', r)

    def test_comment_explains(self):
        text = DF.read_text(encoding='utf-8')
        self.assertIn('free(): invalid pointer', text)
        self.assertIn('TMPDIR', text)

    @unittest.skipIf(sys.platform.startswith('win'), 'needs a POSIX shell')
    def test_wrapper_unsets_tmpdir_and_passes_args(self):
        _, r = block_index()
        fmt = re.search(r"printf '(.*?)' \"\$t\"", r).group(1)
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / 'real-wine'
            real.write_text('#!/bin/sh\necho "T=${TMPDIR-unset}"\nfor a in "$@"; do echo "A=$a"; done\n')
            real.chmod(0o755)
            fmt = fmt.replace('/usr/bin/%s', str(real))
            wrapper = Path(d) / 'wine'
            wrapper.write_text(fmt.replace('\\n', '\n'))
            wrapper.chmod(0o755)
            env = dict(os.environ, TMPDIR='/tmp')
            out = subprocess.run([str(wrapper), 'a b', 'c'], env=env, capture_output=True, text=True)
            self.assertEqual(out.stdout.split('\n')[:3], ['T=unset', 'A=a b', 'A=c'], out.stderr)


if __name__ == '__main__':
    unittest.main()
