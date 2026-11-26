"""DS275: a message names every release a pull request carries (DL-129)."""
import json
import unittest

from _helpers import make_root
import hooklib as H

REG = {"tasks": [{"id": "DS1", "release": 1}, {"id": "DS2", "release": 2}, {"id": "DS3", "rides": "DS2"}]}


class ReleaseNameTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        d = self.root / "docs" / "project"
        d.mkdir(parents=True)
        (d / "registry.json").write_text(json.dumps(REG))

    def test_two_releases(self):
        H.use_record(str(self.root))
        t = {"release_no": 1, "cargo": [{"task": "DS1"}, {"task": "DS3"}]}
        self.assertEqual(H.release_name(t), "RELEASE-1 and RELEASE-2")

    def test_one_release_and_no_record(self):
        H.use_record(str(self.root))
        self.assertEqual(H.release_name({"release_no": 5}), "RELEASE-5")
        H.use_record(str(make_root()))
        self.assertEqual(H.release_name({"release_no": 3, "cargo": [{"task": "DS2"}]}), "RELEASE-3")

    def test_no_word_train_when_a_number_exists(self):
        H.use_record(str(self.root))
        self.assertNotIn("train", H.release_name({"cargo": [{"task": "DS2"}]}).lower())


if __name__ == "__main__":
    unittest.main()
