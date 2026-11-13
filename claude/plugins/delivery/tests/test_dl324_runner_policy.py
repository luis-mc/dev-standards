"""DL324: the Windows runner .env sets PSExecutionPolicyPreference so the runner can load its .ps1 hooks under a ci-*
account that has no execution policy of its own."""
import unittest

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P


class RunnerPolicy(unittest.TestCase):
    def test_env_sets_process_policy(self):
        text = P.windows_env_text('C:/actions-runners/x', 'C:/ProgramData/luismc-delivery/runner-hooks')
        self.assertIn('PSExecutionPolicyPreference=RemoteSigned\n', text.splitlines(keepends=True))

    def test_env_keeps_hooks_first(self):
        lines = P.windows_env_text('C:/actions-runners/x', 'H').splitlines()
        self.assertTrue(lines[0].startswith('ACTIONS_RUNNER_HOOK_JOB_STARTED=H/runner_load_gate.ps1'))
        self.assertEqual(sum(1 for l in lines if l.startswith('PSExecutionPolicyPreference=')), 1)


if __name__ == '__main__':
    unittest.main()
