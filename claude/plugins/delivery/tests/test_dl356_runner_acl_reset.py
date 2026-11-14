"""DL356: the Windows runner files step takes back and resets files already in the runner folder before it locks it,
so files a previous account made (the _work tool cache) stay readable after an account switch."""
import unittest
from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)

import delivery_runner_pool as pool


class FilesStepResetsAcls(unittest.TestCase):
    def test_reset_runs_before_lock(self):
        text = '\n'.join(pool.ps_files('ci-x', 'C:/actions-runners/x', 'C:/ci-tools', 'C:/py/python.exe'))
        take = text.index('takeown /F $folder /R /A /D Y')
        reset = text.index('icacls $folder /reset /T /C /Q')
        lock = text.index('icacls $folder /inheritance:r')
        self.assertLess(take, reset)
        self.assertLess(reset, lock)


if __name__ == '__main__':
    unittest.main()
