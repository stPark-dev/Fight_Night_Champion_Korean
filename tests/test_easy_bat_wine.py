"""한글패치.bat 흐름을 wine 으로 실행해 확인 (wine 이 없으면 skip).

apply.bat·certutil·RPCS3 복호화는 가짜로 바꾼다:
- 가짜 EBOOT.BIN 의 내용이 곧 그 파일의 "SHA-256" 이고, 가짜 certutil(작업 폴더에 둬 cmd 가 먼저 찾음)은 파일 내용을 해시로 출력한다.
- FNC_TEST_DECRYPT 훅은 EBOOT.BIN 을 같은 폴더의 EBOOT.elf 로 복사한다.
- 가짜 apply.bat 은 받은 인자를 args.txt 에 적는다. args.txt 가 없으면 적용 단계 전에 멈춘 것.
"""
import os
import shutil
import subprocess

import pytest

import release

pytestmark = pytest.mark.skipif(not shutil.which("wine"), reason="wine 없음")

JP, US = "a" * 64, "b" * 64
DISC = {"BLJM60267": JP, "BLUS30608": US}
UPDATE_SIZE = 13370336


def win(p):
    return "Z:" + str(p).replace("/", "\\")


def _bat(path, text):
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def _update(hdd0, title, size=UPDATE_SIZE):
    d = hdd0 / "game" / title / "USRDIR"
    d.mkdir(parents=True)
    with open(d / "EBOOT.BIN", "wb") as f:
        f.truncate(size)
    return hdd0 / "game" / title


@pytest.fixture
def env(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "patch").mkdir(parents=True)
    _bat(pkg / "easy.bat", release.easy_bat("vT", DISC).replace("\r\n", "\n"))
    _bat(pkg / "apply.bat", '@echo off\n>"%~dp0args.txt" echo [%~1][%~2]\nexit /b 0\n')
    (pkg / "xdelta3.exe").write_bytes(b"")
    stub = tmp_path / "stub"
    stub.mkdir()
    _bat(stub / "certutil.bat", '@echo off\necho SHA256 hash of %2:\ntype "%~2"\necho.\necho CertUtil: done\n')
    _bat(stub / "decrypt.bat", '@echo off\ncopy /y "%~1" "%~dp1EBOOT.elf" >nul\n')
    game = tmp_path / "my game (1)"
    (game / "PS3_GAME" / "USRDIR").mkdir(parents=True)
    (game / "PS3_GAME" / "PARAM.SFO").write_bytes(b"PSF")
    (game / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text(JP)
    rp = tmp_path / "rpcs3 dir"
    rp.mkdir()

    def run():
        e = dict(os.environ, WINEDEBUG="-all", FNC_TEST_DECRYPT=win(stub / "decrypt.bat"))
        r = subprocess.run(["wine", "cmd", "/c", win(pkg / "easy.bat"), win(game), win(rp)], env=e,
                       input=b"\r\n\r\n", capture_output=True, timeout=180, cwd=stub)
        if os.environ.get("FNC_WINE_DEBUG"):
            print(r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))
        args = pkg / "args.txt"
        return args.read_text(encoding="utf-8", errors="replace").strip() if args.exists() else None

    return {"pkg": pkg, "game": game, "rp": rp, "hdd0": rp / "dev_hdd0", "run": run}


def test_disc_only(env):
    assert env["run"]() == f"[{win(env['game'])}][]"
    assert (env["game"] / "EBOOT.elf").read_text() == JP


def test_same_region_update_is_patched(env):
    u = _update(env["hdd0"], "BLJM60267")
    assert env["run"]() == f"[{win(env['game'])}][{win(u)}]"
    assert (u / "EBOOT.elf").exists()


def test_other_region_update_only_is_ignored(env):
    _update(env["hdd0"], "BLUS30608")
    assert env["run"]() == f"[{win(env['game'])}][]"


def test_both_region_updates_pick_disc_region(env):
    u = _update(env["hdd0"], "BLJM60267")
    _update(env["hdd0"], "BLUS30608")
    assert env["run"]() == f"[{win(env['game'])}][{win(u)}]"


def test_non_102_update_stops(env):
    _update(env["hdd0"], "BLJM60267", size=1000)
    assert env["run"]() is None


def test_unknown_disc_stops(env):
    (env["game"] / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("c" * 64)
    assert env["run"]() is None


def test_stale_elf_is_redecrypted(env):
    (env["game"] / "EBOOT.elf").write_text("broken")
    assert env["run"]() == f"[{win(env['game'])}][]"
    assert (env["game"] / "EBOOT.elf").read_text() == JP


def test_missing_apply_bat_stops_before_decrypt(env):
    (env["pkg"] / "apply.bat").unlink()
    assert env["run"]() is None
    assert not (env["game"] / "EBOOT.elf").exists()


def test_vfs_quoted_dev_hdd0(env):
    hdd0 = env["rp"].parent / "hdd (2) #1"
    u = _update(hdd0, "BLJM60267")
    (env["rp"] / "config").mkdir()
    (env["rp"] / "config" / "vfs.yml").write_text(
        f'$(EmulatorDir): ""\n/dev_hdd0/: "{win(hdd0).replace(chr(92), "/")}/"\n/dev_usb000/: $(EmulatorDir)dev_usb000/\n')
    assert env["run"]() == f"[{win(env['game'])}][{win(u)}]"


def test_vfs_emulator_dir_substitution(env):
    emu = env["rp"].parent / "emu root"
    u = _update(emu / "dev_hdd0", "BLJM60267")
    (env["rp"] / "config").mkdir()
    (env["rp"] / "config" / "vfs.yml").write_text(
        f'$(EmulatorDir): {win(emu).replace(chr(92), "/")}/\n/dev_hdd0/: $(EmulatorDir)dev_hdd0/\n')
    assert env["run"]() == f"[{win(env['game'])}][{win(u)}]"
