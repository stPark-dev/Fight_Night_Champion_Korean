"""배포 패키지: 원본 대비 xdelta 차분 + Windows 적용 배치. 게임 데이터는 넣지 않는다.

  release/FNC_Korean_<버전>/
    patch/boot.big.xdelta, fe.big.xdelta, EBOOT.elf.xdelta   (원본/복호화 EBOOT 기준 차분)
    xdelta3.exe, xdelta3-LICENSE.txt
    apply.bat                                                  (해시 확인 → 적용 → 자막 복제)
    읽어주세요.txt

사용: python tools/release.py <버전> [--xdelta 경로]   (먼저 python tools/build.py translations/ko)
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
XDELTA = Path.home() / "tools" / "xdelta3" / "xdelta3-3.1.0-x86_64.exe"
TARGETS = {  # 배포 이름: (원본 경로, 결과 경로) — 모두 게임 폴더(PS3_GAME 의 부모) 기준
    "boot.big": (build.BOOT_BIG, build.BOOT_BIG),
    "fe.big": (build.FE_BIG, build.FE_BIG),
    "EBOOT.elf": ("EBOOT.elf", build.EBOOT),  # 사용자가 RPCS3 로 복호화한 파일(게임 폴더에 둠)
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bat(version, hashes, subs):
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
    ]
    for name, (src, _) in TARGETS.items():
        lines += [
            f'call :check "%G%\\{win(src)}" {hashes[name]} || exit /b 1',
        ]
    for name, (src, dst) in TARGETS.items():
        lines += [
            f'echo 적용: {name}',
            f'"%X%" -d -f -s "%G%\\{win(src)}" "%P%\\{name}.xdelta" "%G%\\{win(dst)}.ko" || (echo 실패: {name} & exit /b 1)',
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
        ":check",
        'if not exist "%~1" (echo 파일 없음: %~1 & exit /b 1)',
        'for /f "skip=1 delims=" %%h in (\'certutil -hashfile "%~1" SHA256\') do (set "H=%%h" & goto :got)',
        ":got",
        'set "H=%H: =%"',
        'if /i not "%H%"=="%~2" (echo 원본이 다름: %~1 & exit /b 1)',
        "exit /b 0",
    ]
    return "\r\n".join(lines) + "\r\n"


README = """파이트 나이트 챔피언 (PS3, BLJM60267) 한글 패치 {version}

비공식 팬 번역입니다. Electronic Arts 와 무관합니다. 게임 데이터는 들어 있지 않습니다.

[준비]
1. 정품 디스크(BLJM60267)에서 게임 폴더를 추출합니다 (PS3_GAME 폴더가 들어 있는 폴더).
2. RPCS3 의 "도구 > SELF 복호화"(또는 rpcs3.exe --decrypt) 로 PS3_GAME\\USRDIR\\EBOOT.BIN 을 복호화하고,
   결과 EBOOT.elf 를 게임 폴더(PS3_GAME 옆)에 둡니다.

[적용]
  apply.bat "게임 폴더 경로"

  원본 파일이 맞는지 SHA-256 으로 확인한 뒤 boot.big, fe.big, EBOOT 를 바꾸고 영어 자막 파일을 만듭니다.
  바뀐 원본은 같은 자리에 *.orig 로 남습니다.

[주의]
- 패치된 EBOOT.BIN 은 복호화 ELF 라 현재는 RPCS3 전용입니다.
- PS3 시스템 언어가 한국어/일본어/영어일 때 한글로 나옵니다(게임이 영어 데이터를 씀).
- 한글 글꼴: 나눔고딕 Bold, Black Han Sans (SIL Open Font License 1.1).
- xdelta3: Apache License 2.0 (xdelta3-LICENSE.txt).
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--extract", default=ROOT / "work" / "extract")
    ap.add_argument("--elf", default=build.DEFAULT_ELF)
    ap.add_argument("--game", default=ROOT / "build" / "game")
    ap.add_argument("--xdelta", default=XDELTA)
    args = ap.parse_args()
    extract, game = Path(args.extract), Path(args.game)
    out = ROOT / "release" / f"FNC_Korean_{args.version}"
    if out.exists():
        shutil.rmtree(out)
    (out / "patch").mkdir(parents=True)
    srcs = {"boot.big": extract / build.BOOT_BIG, "fe.big": extract / build.FE_BIG, "EBOOT.elf": Path(args.elf)}
    hashes = {}
    for name, (_, dst) in TARGETS.items():
        src, new = srcs[name], game / dst
        hashes[name] = sha256(src)
        subprocess.run([str(args.xdelta), "-e", "-9", "-S", "djw", "-f", "-s", str(src), str(new),
                        str(out / "patch" / f"{name}.xdelta")], check=True)
        # 검증: 차분을 다시 적용하면 같은 파일이 나와야 한다
        chk = out / "patch" / f"_{name}.chk"
        subprocess.run([str(args.xdelta), "-d", "-f", "-s", str(src), str(out / "patch" / f"{name}.xdelta"), str(chk)],
                       check=True)
        if sha256(chk) != sha256(new):
            raise RuntimeError(f"{name}: 차분 검증 실패")
        chk.unlink()
        print(f"{name}.xdelta  {(out / 'patch' / f'{name}.xdelta').stat().st_size:,} B")
    fmv = extract / build.FMV_DIR
    subs = [(f"{build.FMV_DIR}/{f.name}", f"{build.FMV_DIR}/{f.name[:-len('_fre.sub')]}_eng.sub")
            for f in sorted(fmv.glob("*_fre.sub"))]
    (out / "apply.bat").write_bytes(bat(args.version, hashes, subs).encode("utf-8"))
    (out / "읽어주세요.txt").write_text(README.format(version=args.version), encoding="utf-8-sig")
    shutil.copy(args.xdelta, out / "xdelta3.exe")
    (out / "xdelta3-LICENSE.txt").write_text(
        "xdelta3 3.1.0 — Copyright (C) Joshua MacDonald. Licensed under the Apache License, Version 2.0.\n"
        "http://www.apache.org/licenses/LICENSE-2.0\nSource: https://github.com/jmacd/xdelta\n", encoding="utf-8")
    shutil.copy(ROOT / "NOTICE", out / "NOTICE.txt")
    print(out)


if __name__ == "__main__":
    main()
