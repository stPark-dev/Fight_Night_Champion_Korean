"""배포 패키지: 두 판(일본 BLJM60267 / 북미 BLUS30608) 원본 대비 xdelta 차분 + Windows 적용 배치.
게임 데이터는 넣지 않는다.

  release/FNC_Korean_<버전>/
    patch/<타이틀ID>/boot.big.xdelta, fe.big.xdelta, EBOOT.elf.xdelta   (그 판 원본/복호화 EBOOT 기준 차분)
    xdelta3.exe, xdelta3-COPYING.txt, xdelta3-3.1.0.tar.gz              (xdelta 3.1.0 — GPL v2, 소스 동봉)
    apply.bat                                                            (EBOOT 해시로 판 판별 → 원본 확인 → 적용 → 자막 생성)
    읽어주세요.txt, NOTICE.txt

사용: python tools/release.py <버전>
      (먼저 두 판 모두 빌드: python tools/build.py translations/ko
                            python tools/build.py translations/ko --extract work/extract_us --elf work/eboot_us/EBOOT.elf --out build/game_us)
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
TOOLS = ROOT / "work" / "tools" / "xdelta"
if os.name == "nt":
    XDELTA = Path.home() / "tools" / "xdelta3" / "xdelta3-3.1.0-x86_64.exe"
    XDELTA_EXE = XDELTA
else:
    XDELTA = TOOLS / "xdelta3-3.1.0" / "xdelta3"  # 소스(xdelta3-3.1.0.tar.gz)에서 빌드한 것
    XDELTA_EXE = TOOLS / "xdelta3-3.1.0-x86_64.exe"
XDELTA_SRC = TOOLS / "xdelta3-3.1.0.tar.gz"  # https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0

TARGETS = {  # 배포 이름: (원본 경로, 결과 경로) — 모두 게임 폴더(PS3_GAME 의 부모) 기준
    "boot.big": (build.BOOT_BIG, build.BOOT_BIG),
    "fe.big": (build.FE_BIG, build.FE_BIG),
    "EBOOT.elf": ("EBOOT.elf", build.EBOOT),  # 사용자가 RPCS3 로 복호화한 파일(게임 폴더에 둠)
}
REGIONS = {  # 타이틀 ID: 저장소 기준 경로
    "BLJM60267": {"extract": "work/extract", "elf": "work/eboot/EBOOT.elf", "game": "build/game"},
    "BLUS30608": {"extract": "work/extract_us", "elf": "work/eboot_us/EBOOT.elf", "game": "build/game_us"},
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bat(version, regions, subs):
    """regions: {타이틀ID: {배포 이름: 원본 sha256}}. EBOOT.elf 해시로 판을 고른 뒤 그 판의 나머지 원본을 확인."""
    win = lambda p: p.replace("/", "\\")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal",
        f"echo 파이트 나이트 챔피언 한글 패치 {version}",
        'if "%~1"=="" (echo 사용: apply.bat ^<게임 폴더^>   ^(PS3_GAME 이 들어 있는 폴더^) & exit /b 1)',
        'set "G=%~1"',
        'set "P=%~dp0patch"',
        'set "X=%~dp0xdelta3.exe"',
        'if not exist "%G%\\EBOOT.elf" (echo 먼저 RPCS3 로 EBOOT.BIN 을 복호화해 게임 폴더에 EBOOT.elf 로 두십시오. & exit /b 1)',
        'call :hash "%G%\\EBOOT.elf" || exit /b 1',
        'set "R="',
    ]
    for title, hashes in regions.items():
        lines.append(f'if /i "%H%"=="{hashes["EBOOT.elf"]}" set "R={title}"')
    lines += [
        f'if not defined R (echo 지원하지 않는 EBOOT.elf 입니다. 지원 디스크: {", ".join(regions)} — 원본 EBOOT.BIN 을 복호화한 파일인지 확인하십시오. & exit /b 1)',
        "echo 디스크: %R%",
        "goto :region_%R%",
    ]
    for title, hashes in regions.items():
        lines.append(f":region_{title}")
        for name, (src, _) in TARGETS.items():
            if name != "EBOOT.elf":
                lines.append(f'call :check "%G%\\{win(src)}" {hashes[name]} || exit /b 1')
        lines.append("goto :apply")
    lines.append(":apply")
    for name, (src, dst) in TARGETS.items():
        lines += [
            f'echo 적용: {name}',
            f'"%X%" -d -f -s "%G%\\{win(src)}" "%P%\\%R%\\{name}.xdelta" "%G%\\{win(dst)}.ko" || (echo 실패: {name} & exit /b 1)',
        ]
    for name, (_, dst) in TARGETS.items():
        d = win(dst)
        lines += [f'if not exist "%G%\\{d}.orig" move "%G%\\{d}" "%G%\\{d}.orig" >nul',
                  f'move /y "%G%\\{d}.ko" "%G%\\{d}" >nul']
    lines.append("echo 자막 파일 만들기")
    for fre, eng in subs:
        lines.append(f'copy /y "%G%\\{win(fre)}" "%G%\\{win(eng)}" >nul')
    lines += [
        "echo 완료. 원본은 *.orig 로 남겨 두었습니다.",
        "exit /b 0",
        "",
        ":hash",
        'if not exist "%~1" (echo 파일 없음: %~1 & exit /b 1)',
        'set "H="',
        "for /f \"skip=1 delims=\" %%h in ('certutil -hashfile \"%~1\" SHA256') do if not defined H set \"H=%%h\"",
        'set "H=%H: =%"',
        "exit /b 0",
        "",
        ":check",
        'call :hash "%~1" || exit /b 1',
        'if /i not "%H%"=="%~2" (echo 원본이 다름: %~1 & exit /b 1)',
        "exit /b 0",
    ]
    return "\r\n".join(lines) + "\r\n"


README = """파이트 나이트 챔피언 (PS3) 한글 패치 {version}

비공식 팬 번역입니다. Electronic Arts 와 무관합니다. 게임 데이터는 들어 있지 않습니다.

[지원 디스크]
- 일본판 BLJM60267 (v01.01)
- 북미판 BLUS30608 (v01.00)
apply.bat 이 EBOOT 로 판을 알아내 맞는 패치를 적용합니다.

[준비]
1. 정품 디스크에서 게임 폴더를 추출합니다 (PS3_GAME 폴더가 들어 있는 폴더).
2. RPCS3 의 "도구 > SELF 복호화"(또는 rpcs3.exe --decrypt) 로 PS3_GAME\\USRDIR\\EBOOT.BIN 을 복호화하고,
   결과 EBOOT.elf 를 게임 폴더(PS3_GAME 옆)에 둡니다.

[적용]
  apply.bat "게임 폴더 경로"

  원본 파일이 맞는지 SHA-256 으로 확인한 뒤 boot.big, fe.big, EBOOT 를 바꾸고 영어 자막 파일을 만듭니다.
  바뀐 원본은 같은 자리에 *.orig 로 남습니다.

[주의]
- 패치된 EBOOT.BIN 은 복호화 ELF 라 현재는 RPCS3 전용입니다.
- PS3 시스템 언어가 한국어/일본어/영어일 때 한글로 나옵니다(게임이 영어 데이터를 씀).
- 게임 업데이트가 설치돼 있으면 업데이트의 EBOOT 가 실행돼 자막·날짜 등 EBOOT 패치가 적용되지 않습니다.
- 한글 글꼴: 나눔고딕 Bold, Black Han Sans (SIL Open Font License 1.1).
- xdelta3 3.1.0: GNU GPL v2 (xdelta3-COPYING.txt). 대응 소스 xdelta3-3.1.0.tar.gz 를 함께 넣었습니다.
"""


def package(version, out_root, xdelta=XDELTA, xdelta_exe=XDELTA_EXE, xdelta_src=XDELTA_SRC, regions=None):
    regions = regions or REGIONS
    out = Path(out_root) / f"FNC_Korean_{version}"
    if out.exists():
        shutil.rmtree(out)
    hashes, subs_by_region = {}, {}
    for title, r in regions.items():
        extract, elf, game = (ROOT / r["extract"]), (ROOT / r["elf"]), (ROOT / r["game"])
        if build.title_id(extract) != title or build.title_id(game) != title:
            raise ValueError(f"{title}: 추출본/빌드 결과의 타이틀 ID 가 다름")
        (out / "patch" / title).mkdir(parents=True)
        srcs = {"boot.big": extract / build.BOOT_BIG, "fe.big": extract / build.FE_BIG, "EBOOT.elf": elf}
        hashes[title] = {}
        for name, (_, dst) in TARGETS.items():
            src, new, diff = srcs[name], game / dst, out / "patch" / title / f"{name}.xdelta"
            hashes[title][name] = sha256(src)
            subprocess.run([str(xdelta), "-e", "-9", "-S", "djw", "-f", "-s", str(src), str(new), str(diff)], check=True)
            # 검증: 차분을 다시 적용하면 같은 파일이 나와야 한다
            chk = diff.with_suffix(".chk")
            subprocess.run([str(xdelta), "-d", "-f", "-s", str(src), str(diff), str(chk)], check=True)
            if sha256(chk) != sha256(new):
                raise RuntimeError(f"{title} {name}: 차분 검증 실패")
            chk.unlink()
            print(f"{title}/{name}.xdelta  {diff.stat().st_size:,} B")
        fmv = extract / build.FMV_DIR
        subs_by_region[title] = [(f"{build.FMV_DIR}/{f.name}", f"{build.FMV_DIR}/{f.name[:-len('_fre.sub')]}_eng.sub")
                                 for f in sorted(fmv.glob("*_fre.sub"))]
    subs = next(iter(subs_by_region.values()))
    if any(s != subs for s in subs_by_region.values()):
        raise ValueError("판마다 자막 파일 구성이 다름 — 배치 하나로 처리할 수 없음")
    (out / "apply.bat").write_bytes(bat(version, hashes, subs).encode("utf-8"))
    (out / "읽어주세요.txt").write_text(README.format(version=version), encoding="utf-8-sig")
    shutil.copy(xdelta_exe, out / "xdelta3.exe")
    shutil.copy(xdelta_src, out / "xdelta3-3.1.0.tar.gz")
    with tarfile.open(xdelta_src) as tf:
        copying = tf.extractfile("xdelta3-3.1.0/COPYING").read().decode("latin-1")
    (out / "xdelta3-COPYING.txt").write_text(
        "xdelta3 3.1.0 — Copyright (C) Joshua MacDonald. GNU General Public License v2.\n"
        "Corresponding source: xdelta3-3.1.0.tar.gz (this package), "
        "https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0\n\n" + copying, encoding="utf-8")
    shutil.copy(ROOT / "NOTICE", out / "NOTICE.txt")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--out", default=ROOT / "release")
    ap.add_argument("--xdelta", default=XDELTA, help="차분 생성·검증에 쓸 xdelta3 (이 OS 용)")
    ap.add_argument("--xdelta-exe", default=XDELTA_EXE, help="패키지에 넣을 Windows 용 xdelta3.exe")
    ap.add_argument("--xdelta-src", default=XDELTA_SRC, help="xdelta3-3.1.0.tar.gz (GPL 대응 소스)")
    args = ap.parse_args()
    print(package(args.version, args.out, args.xdelta, args.xdelta_exe, args.xdelta_src))


if __name__ == "__main__":
    main()
