#!/usr/bin/env python3
"""safe_eval in convert_interim_record.py accepts literals and dict(name=literal) only (DS163)."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
import convert_interim_record as cir  # noqa: E402


def ev(src: str):
    return cir.safe_eval(ast.parse(src, mode="eval").body)


class SafeEvalTests(unittest.TestCase):
    def test_literals(self):
        self.assertEqual(ev("[1, 'a', (2, 3), {'k': None}]"), [1, "a", (2, 3), {"k": None}])

    def test_dict_call_with_keywords(self):
        self.assertEqual(ev("dict(a=1)"), {"a": 1})

    def test_nested(self):
        self.assertEqual(ev("[dict(a=dict(b=[1, 2]), c='x')]"), [{"a": {"b": [1, 2]}, "c": "x"}])

    def test_everything_else_is_refused(self):
        for src in ("().__class__", "().__class__.__bases__[0]", "open('x')", "dict(a=len('x'))",
                    "dict(**{'a': 1})", "dict([('a', 1)])", "name", "dict(a=().__class__)", "{**x}"):
            with self.subTest(src=src), self.assertRaises(ValueError):
                ev(src)


if __name__ == "__main__":
    unittest.main()
