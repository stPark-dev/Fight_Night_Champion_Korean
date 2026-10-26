import subprocess
from pathlib import Path

import pytest

import build
import release

ROOT = Path(__file__).resolve().parents[1]
H = {"boot.big": "a" * 64, "fe.big": "b" * 64, "EBOOT.elf": "c" * 64}
H2 = {"boot.big": "a" * 64, "fe.big": "d" * 64, "EBOOT.elf": "e" * 64}
SUBS = [("PS3_GAME/USRDIR/data/common/fmv/mm_1_fre.sub", "PS3_GAME/USRDIR/data/common/fmv/mm_1_eng.sub")]


def test_bat_selects_region_by_eboot_hash():
    text = release.bat("v1", {"BLJM60267": H, "BLUS30608": H2}, SUBS)
    assert "\r\n" in text
    # 판별: EBOOT 해시 → 판
    assert f'"{H["EBOOT.elf"]}"' in text and f'"{H2["EBOOT.elf"]}"' in text
    assert 'set "R=BLJM60267"' in text and 'set "R=BLUS30608"' in text
    # 판별 뒤 그 판 원본 해시로 나머지 확인, 그 판 차분 폴더 사용
    assert H2["fe.big"] in text and "%P%\\%R%\\fe.big.xdelta" in text
    assert "mm_1_eng.sub" in text


def test_bat_rejects_unknown_eboot():
    text = release.bat("v1", {"BLJM60267": H, "BLUS30608": H2}, SUBS)
    assert "지원하지 않는 EBOOT" in text


def test_readme_lists_both_discs_and_gpl():
    text = release.README.format(version="v1")
    assert "BLJM60267" in text and "BLUS30608" in text
    assert "GPL" in text and "Apache" not in text


XDELTA = ROOT / "work/tools/xdelta/xdelta3-3.1.0/xdelta3"
GAMES = {t: (ROOT / r["game"]) for t, r in release.REGIONS.items()}


@pytest.mark.skipif(not XDELTA.exists() or not all(g.exists() for g in GAMES.values()),
                    reason="xdelta3 빌드본 또는 두 판 빌드 결과 없음")
def test_package_roundtrip(tmp_path):
    out = release.package("vtest", tmp_path, xdelta=XDELTA,
                          xdelta_exe=ROOT / "work/tools/xdelta/xdelta3-3.1.0-x86_64.exe",
                          xdelta_src=ROOT / "work/tools/xdelta/xdelta3-3.1.0.tar.gz")
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    for title in release.REGIONS:
        for n in ("boot.big", "fe.big", "EBOOT.elf"):
            assert f"patch/{title}/{n}.xdelta" in names
    assert {"apply.bat", "xdelta3.exe", "xdelta3-COPYING.txt", "xdelta3-3.1.0.tar.gz",
            "읽어주세요.txt", "NOTICE.txt"} <= names
    # 북미판 차분을 북미판 원본에 적용하면 북미판 빌드 결과와 같아야 한다
    r = release.REGIONS["BLUS30608"]
    dst = tmp_path / "fe.chk"
    subprocess.run([str(XDELTA), "-d", "-f", "-s", str(ROOT / r["extract"] / build.FE_BIG),
                    str(out / "patch/BLUS30608/fe.big.xdelta"), str(dst)], check=True)
    assert dst.read_bytes() == (ROOT / r["game"] / build.FE_BIG).read_bytes()
