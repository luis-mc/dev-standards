#!/usr/bin/env python3
"""safe_eval in convert_interim_record.py accepts literals and dict(name=literal) only (DS163)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
import convert_interim_record as cir  # noqa: E402


def ev(src: str):
    return cir.safe_eval(ast.parse(src, mode="eval").body)


def test_literals():
    assert ev("[1, 'a', (2, 3), {'k': None}]") == [1, "a", (2, 3), {"k": None}]


def test_dict_call_with_keywords():
    assert ev("dict(a=1)") == {"a": 1}


def test_nested():
    assert ev("[dict(a=dict(b=[1, 2]), c='x')]") == [{"a": {"b": [1, 2]}, "c": "x"}]


@pytest.mark.parametrize("src", [
    "().__class__", "().__class__.__bases__[0]", "open('x')", "dict(a=len('x'))",
    "dict(**{'a': 1})", "dict([('a', 1)])", "name", "dict(a=().__class__)", "{**x}",
])
def test_everything_else_is_refused(src):
    with pytest.raises(ValueError):
        ev(src)
