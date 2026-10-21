import pseudoloc
from fnc.t3db import Row


def rows(*items):
    return [Row(i, t, n, 0) for n, (i, t) in enumerate(items)]


def test_ksx1001_has_2350_hangul():
    s = pseudoloc.ksx1001_hangul()
    assert len(s) == 2350 and len(set(s)) == 2350
    assert s[0] == "가" and s[-1] == "힝"


def test_original_kept_as_prefix_and_suffix_is_hangul():
    out = pseudoloc.generate(rows(("TXT_A", "Load %1s <0>{c0}\nNow")))
    t = out["TXT_A"]
    assert t.startswith("Load %1s <0>{c0}\nNow ")
    assert all(0xAC00 <= ord(c) <= 0xD7A3 for c in t.split(" ")[-1])


def test_skips_online_and_null():
    out = pseudoloc.generate(rows(("OSDK_X", "Online"), ("TXT_N", None), ("TXT_B", "Hi")))
    assert set(out) == {"TXT_B"}


def test_cycles_through_all_syllables():
    many = rows(*[(f"TXT_{i}", "Some menu text here") for i in range(600)])
    used = {c for t in pseudoloc.generate(many).values() for c in t if ord(c) >= 0xAC00}
    assert used == set(pseudoloc.ksx1001_hangul())
