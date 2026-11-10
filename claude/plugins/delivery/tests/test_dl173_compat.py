"""DL173: delivery_doctor plugins.compat reads the installed plugin cache and warns on a version that does not fit."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import L, make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_doctor as D


def cache_with(base, plugins):
    """plugins: {name: [versions]} under <base>/<marketplace>/<name>/<version>/."""
    for name, versions in plugins.items():
        for v in versions:
            (Path(base) / "dev-standards" / name / v).mkdir(parents=True)


COMPAT = {"requires": {"luismc-artifacts": {"luismc-delivery": {"version": ">=1.18.0", "why": "ledger"}}}}


class Compat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dl173-")
        self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.cache)
        self.compat = os.path.join(self.tmp, "compat.json")
        Path(self.compat).write_text(json.dumps(COMPAT), encoding="utf-8")

    def items(self):
        return D.compat_items(D.installed_versions(self.cache), self.compat)

    def test_meets(self):
        cache_with(self.cache, {"luismc-artifacts": ["1.3.3"], "luismc-delivery": ["1.17.0", "1.20.2"]})
        self.assertEqual(self.items(), [])

    def test_highest_version_is_picked(self):
        cache_with(self.cache, {"luismc-delivery": ["1.9.0", "1.20.2", "1.10.0"]})
        self.assertEqual(D.installed_versions(self.cache)["luismc-delivery"], "1.20.2")

    def test_fails(self):
        cache_with(self.cache, {"luismc-artifacts": ["1.3.3"], "luismc-delivery": ["1.17.9"]})
        items = self.items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "warn")
        self.assertIn("claude plugin update luismc-delivery@dev-standards", items[0]["detail"])

    def test_plugin_absent(self):
        cache_with(self.cache, {"luismc-artifacts": ["1.3.3"]})
        self.assertEqual(self.items(), [])
        self.assertEqual(D.compat_items({}, self.compat), [])

    def test_no_cache_folder(self):
        self.assertEqual(D.installed_versions(os.path.join(self.tmp, "none")), {})

    def test_check_warns_but_passes(self):
        cache_with(self.cache, {"luismc-artifacts": ["1.3.3"], "luismc-delivery": ["1.0.0"]})
        with mock.patch.dict(os.environ, {"DELIVERY_PLUGIN_CACHE": self.cache}), \
                mock.patch.object(D, "PLUGIN", os.path.join(self.tmp, "p")):
            os.makedirs(os.path.join(self.tmp, "p", "references"))
            Path(self.tmp, "p", "references", "plugin-compat.json").write_text(json.dumps(COMPAT), encoding="utf-8")
            res = D.check_plugins(self.tmp, {})
        self.assertTrue(res[0])
        self.assertTrue(res[1].startswith("WARN"))

    def test_shipped_file_is_valid(self):
        data = json.loads(Path(D.PLUGIN, "references", "plugin-compat.json").read_text(encoding="utf-8"))
        for plugin, needs in data["requires"].items():
            for other, rule in needs.items():
                self.assertTrue(rule["version"].startswith(">="))
                self.assertTrue(rule["why"])


if __name__ == "__main__":
    unittest.main()
