from pathlib import Path

import pytest

from fnc import edat

ROOT = Path(__file__).resolve().parents[1]
US = ROOT / "work/updates/us_102/USRDIR/dlc_pack1"
JP = ROOT / "work/updates/jp_102/USRDIR/dlc_pack1"
KLIC = edat.FNC_KLIC


def _need(*paths):
    for p in paths:
        if not p.exists():
            pytest.skip(f"{p.relative_to(ROOT)} 없음 (work/updates 에 1.02 업데이트 추출 필요)")
    return [p.read_bytes() for p in paths]


def test_klic_validates_header():
    us, = _need(US / "dlc.toc.edat")
    assert edat.klic_ok(us, KLIC)
    assert not edat.klic_ok(us, bytes(16))


def test_wrong_klic_rejected():
    us, = _need(US / "dlc.toc.edat")
    with pytest.raises(ValueError):
        edat.decrypt(us, bytes(16))


@pytest.mark.parametrize("name", ["dlc.toc", "info.dlc", "dlc/data/ps3/dlc_main.big"])
def test_us_decrypts_to_jp_plain(name):
    us, jp = _need(US / f"{name}.edat", JP / name)
    assert edat.decrypt(us, KLIC) == jp


@pytest.mark.parametrize("name", ["dlc.toc", "dlc/data/ps3/dlc_main.big"])
def test_reencrypt_same_plaintext_is_identical(name):
    us, = _need(US / f"{name}.edat")
    assert edat.encrypt_like(us, edat.decrypt(us, KLIC), KLIC) == us


def test_reencrypt_changed_and_resized():
    us, = _need(US / "dlc/data/ps3/dlc_main.big.edat")
    plain = edat.decrypt(us, KLIC)
    new_plain = plain[:100000] + b"KOREAN" * 7000 + plain[100000:]
    out = edat.encrypt_like(us, new_plain, KLIC)
    assert edat.decrypt(out, KLIC) == new_plain
    assert edat.klic_ok(out, KLIC)
    # 바뀌지 않은 앞쪽 블록은 암호문도 그대로 (차분 패치 크기가 작아짐)
    assert out[:0x100 + 6 * (0x20 + 0x4000)][0xC0:] == us[:0x100 + 6 * (0x20 + 0x4000)][0xC0:]
