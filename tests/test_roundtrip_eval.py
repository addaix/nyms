"""Tests for the surrogate round-trip measurement script (misc/eval/roundtrip.py).

The script lives outside the package, so it is imported by path. These tests run no model:
they feed hand-written outputs to the measurement function.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "misc" / "eval" / "roundtrip.py"


@pytest.fixture(scope="module")
def rt():
    spec = importlib.util.spec_from_file_location("nyms_roundtrip_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def en_names(rt):
    p, _, issued = rt._pseudonymised("en", "keyed-names")
    names = [s for s in issued if not s.startswith("[")]
    return p, issued, names


def test_shortened_repeated_word_name_counts_once(rt, en_names):
    p, issued, names = en_names
    (repeated,) = [s for s in names if len(set(s.split())) == 1]  # e.g. "Zodiac Zodiac"
    word = repeated.split()[0]
    assert rt._measure(p, issued, f"Dear Mr {word}, thanks.")["mangled"] == 1


def test_each_leftover_fragment_counts_once(rt, en_names):
    p, issued, names = en_names
    first, last = [s for s in names if len(set(s.split())) == 2][0].split()
    output = f"Ms {first} wrote. {last} {first} agreed. {last} too."
    assert rt._measure(p, issued, output)["mangled"] == 3


def test_full_names_are_not_mangled(rt, en_names):
    p, issued, names = en_names
    m = rt._measure(p, issued, " and ".join(names))
    assert m["mangled"] == 0
    assert m["kept"] == len(names)
