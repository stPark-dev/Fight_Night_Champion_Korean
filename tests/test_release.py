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


# --- 타이틀 업데이트 1.02 -----------------------------------------------

UPD_JP = [("EBOOT.elf", "EBOOT.elf", "USRDIR/EBOOT.BIN", "1" * 64),
          ("dlc_main.big", "USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big", "USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big", "2" * 64),
          ("dlc.toc", "USRDIR/dlc_pack1/dlc.toc", "USRDIR/dlc_pack1/dlc.toc", "3" * 64)]
UPD_US = [("EBOOT.elf", "EBOOT.elf", "USRDIR/EBOOT.BIN", "4" * 64),
          ("dlc_main.big.edat", "USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big.edat",
           "USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big.edat", "5" * 64),
          ("dlc.toc.edat", "USRDIR/dlc_pack1/dlc.toc.edat", "USRDIR/dlc_pack1/dlc.toc.edat", "6" * 64)]


def _bat_with_updates():
    return release.bat("v1", {"BLJM60267": H, "BLUS30608": H2}, SUBS,
                       updates={"BLJM60267": UPD_JP, "BLUS30608": UPD_US})


def test_bat_update_is_optional_second_argument():
    text = _bat_with_updates()
    assert 'if "%~2"==""' in text and 'set "U=%~2"' in text
    assert "%U%\\EBOOT.elf" in text
    # 업데이트 EBOOT 해시로 업데이트 판 판별, 디스크 판과 다르면 중단
    assert f'"{"1" * 64}"' in text and f'"{"4" * 64}"' in text
    assert "%UR%" in text and "판이 다릅니다" in text
    # 북미판 DLC 는 .edat
    assert "dlc_main.big.edat" in text and "%P%\\%R%\\update\\dlc_main.big.edat.xdelta" in text


def test_bat_checks_all_hashes_before_writing():
    text = _bat_with_updates()
    first_write = min(text.index('"%X%" -d'), text.index("move "))
    for sha in ("2" * 64, "3" * 64, "5" * 64, "6" * 64, H["fe.big"], H2["fe.big"]):
        assert text.index(sha) < first_write


def test_bat_without_updates_still_works():
    text = release.bat("v1", {"BLJM60267": H, "BLUS30608": H2}, SUBS)
    assert 'set "U=' not in text


def test_readme_mentions_update():
    text = release.README.format(version="v1")
    assert "1.02" in text and "업데이트 폴더" in text and "01.00" in text and "01.01" not in text


UPD_GAMES = {t: ROOT / r["update_game"] for t, r in release.REGIONS.items()}


@pytest.mark.skipif(not XDELTA.exists() or not all(g.exists() for g in list(GAMES.values()) + list(UPD_GAMES.values())),
                    reason="xdelta3 빌드본 또는 두 판(+업데이트) 빌드 결과 없음")
def test_package_includes_update_patches(tmp_path):
    out = release.package("vtest", tmp_path, xdelta=XDELTA,
                          xdelta_exe=ROOT / "work/tools/xdelta/xdelta3-3.1.0-x86_64.exe",
                          xdelta_src=ROOT / "work/tools/xdelta/xdelta3-3.1.0.tar.gz")
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert {"patch/BLJM60267/update/EBOOT.elf.xdelta", "patch/BLJM60267/update/dlc_main.big.xdelta",
            "patch/BLJM60267/update/dlc.toc.xdelta", "patch/BLUS30608/update/EBOOT.elf.xdelta",
            "patch/BLUS30608/update/dlc_main.big.edat.xdelta", "patch/BLUS30608/update/dlc.toc.edat.xdelta"} <= names
    r = release.REGIONS["BLUS30608"]
    rel = "USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big.edat"
    dst = tmp_path / "main.chk"
    subprocess.run([str(XDELTA), "-d", "-f", "-s", str(ROOT / r["update"] / rel),
                    str(out / "patch/BLUS30608/update/dlc_main.big.edat.xdelta"), str(dst)], check=True)
    assert dst.read_bytes() == (ROOT / r["update_game"] / rel).read_bytes()


# --- 리뷰 반영 (재실행·부분 적용·괄호 경로) ------------------------------

def test_bat_uses_orig_as_source_when_present():
    """이미 패치된 폴더에서 다시 실행(업데이트 폴더 추가 등)해도 .orig 를 원본으로 써서 막히지 않는다."""
    text = _bat_with_updates()
    assert 'if exist "%S%.orig" set "S=%S%.orig"' in text
    assert '"%X%" -d -f -s "%S%"' in text
    assert 'call :check "%S%"' in text


def test_bat_decodes_everything_before_moving_anything():
    text = _bat_with_updates()
    last_decode = text.rindex('"%X%" -d')
    first_move = text.index("move ")
    assert last_decode < first_move


def test_bat_messages_quote_paths():
    text = _bat_with_updates()
    assert 'echo 파일 없음: "%~1"' in text and 'echo 원본이 다름: "%~1"' in text


def test_bat_rejects_duplicate_update_hashes():
    same = [(n, s, d, "1" * 64 if n == "EBOOT.elf" else h) for n, s, d, h in UPD_US]
    with pytest.raises(ValueError):
        release.bat("v1", {"BLJM60267": H, "BLUS30608": H2}, SUBS, updates={"BLJM60267": UPD_JP, "BLUS30608": same})


@pytest.mark.skipif(not XDELTA.exists() or not all(g.exists() for g in list(GAMES.values()) + list(UPD_GAMES.values())),
                    reason="xdelta3 빌드본 또는 두 판(+업데이트) 빌드 결과 없음")
def test_package_rejects_stale_update_build(tmp_path):
    import shutil
    regions = {t: dict(r) for t, r in release.REGIONS.items()}
    stale = tmp_path / "stale_update"
    shutil.copytree(ROOT / regions["BLJM60267"]["update_game"], stale, copy_function=lambda s, d: shutil.copy(s, d))
    toc = stale / "USRDIR/dlc_pack1/dlc.toc"
    toc.write_bytes(toc.read_bytes()[:-1] + b"\0")
    regions["BLJM60267"]["update_game"] = str(stale)
    with pytest.raises(ValueError):
        release.package("vtest", tmp_path, xdelta=XDELTA,
                        xdelta_exe=ROOT / "work/tools/xdelta/xdelta3-3.1.0-x86_64.exe",
                        xdelta_src=ROOT / "work/tools/xdelta/xdelta3-3.1.0.tar.gz", regions=regions)


def test_readme_uses_real_rpcs3_menu_names_and_move_step():
    """RPCS3 GUI 에는 한국어 번역이 없다 — 실제 영어 메뉴 이름을 쓰고, EBOOT.elf 를 옮기라고 안내한다."""
    text = release.README.format(version="v1")
    for label in ("Utilities > Decrypt PS3 Binaries", "File > Install Packages/Raps/Edats",
                  "File > Add Games", "Console Language"):
        assert label in text
    assert "SELF 복호화" not in text and "옮깁니다" in text


# --- 간편 적용 (한글패치.bat) -------------------------------------------

def test_easy_bat_flow():
    text = release.easy_bat("v1", {"BLJM60267": "a" * 64})
    assert "\r\n" in text and text.startswith("@echo off")
    # 인자가 없으면 폴더 선택 창, PowerShell 이 없으면 직접 입력
    assert "FolderBrowserDialog" in text and "set /p" in text
    # RPCS3 로 복호화: GUI 프로그램이라 start /wait, 원본은 .orig 우선, 임시 폴더에서
    assert 'start "" /wait "%RP%\\rpcs3.exe" --no-gui --decrypt' in text
    assert 'if exist "%~1.orig" set "SRC=%~1.orig"' in text
    # dev_hdd0 위치: config\vfs.yml → vfs.yml → 기본값
    assert "config\\vfs.yml" in text and "/dev_hdd0/:" in text and "$(EmulatorDir)" in text
    # 업데이트 1.02 자동 감지 후 apply.bat 호출
    assert "13370336" in text  # 업데이트 1.02 EBOOT.BIN 크기로 감지
    assert 'call "%HERE%apply.bat" "%G%" "%U%"' in text and 'call "%HERE%apply.bat" "%G%"' in text
    # RPCS3 가 실행 중이면 중단, 창이 바로 닫히지 않게 pause
    assert "rpcs3.exe" in text and "pause" in text


def test_package_has_easy_bat_and_readme_simple_steps(tmp_path):
    text = release.README.format(version="v1")
    assert "한글패치.bat" in text and "7-Zip" in text


def test_zip_marks_korean_names_utf8(tmp_path):
    """한글 파일 이름(한글패치.bat, 읽어주세요.txt)이 Windows 기본 압축 풀기에서 깨지지 않도록 UTF-8 표시."""
    import zipfile
    d = tmp_path / "FNC_Korean_v0.9.6"
    (d / "patch").mkdir(parents=True)
    (d / "한글패치.bat").write_text("x")
    (d / "patch" / "a.xdelta").write_bytes(b"1")
    z = release.zip_package(d)
    assert z.name == "FNC_Korean_v0.9.6.zip"
    with zipfile.ZipFile(z) as f:
        info = {i.filename: i for i in f.infolist()}
        assert set(info) == {"한글패치.bat", "patch/a.xdelta"}
        assert info["한글패치.bat"].flag_bits & 0x800
