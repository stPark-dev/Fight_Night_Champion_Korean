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
REGIONS = {  # 타이틀 ID: 저장소 기준 경로 (update*: 타이틀 업데이트 1.02 — 설치 폴더 기준)
    "BLJM60267": {"extract": "work/extract", "elf": "work/eboot/EBOOT.elf", "game": "build/game",
                  "update": "work/updates/jp_102", "update_elf": "work/eboot_jp102/EBOOT.elf",
                  "update_game": "build/game_update"},
    "BLUS30608": {"extract": "work/extract_us", "elf": "work/eboot_us/EBOOT.elf", "game": "build/game_us",
                  "update": "work/updates/us_102", "update_elf": "work/eboot_us102/EBOOT.elf",
                  "update_game": "build/game_us_update"},
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_targets(update_dir):
    """업데이트 폴더 기준 [(배포 이름, 원본 경로, 결과 경로)]. 북미판 DLC 는 .edat."""
    out = [("EBOOT.elf", "EBOOT.elf", build.UPDATE_EBOOT)]  # 사용자가 업데이트 EBOOT.BIN 을 복호화해 둔 파일
    for rel in (build.DLC_MAIN, build.DLC_TOC):
        path, encrypted = build._dlc_path(update_dir, rel)
        rel = f"{rel}.edat" if encrypted else rel
        out.append((Path(rel).name, rel, rel))
    return out


def bat(version, regions, subs, updates=None):
    """regions: {타이틀ID: {배포 이름: 원본 sha256}}. EBOOT.elf 해시로 판을 고른 뒤 그 판의 나머지 원본을 확인.
    updates: {타이틀ID: [(배포 이름, 원본 경로, 결과 경로, 원본 sha256)]} — 두 번째 인자(업데이트 폴더)를 받으면 적용.
    순서: 모든 해시 확인 → 모든 .ko 디코드 → 마지막에 한꺼번에 이동. 원본은 *.orig 가 있으면 그것을 쓴다
    (이미 패치한 폴더에 다시 실행하거나, 업데이트 폴더를 나중에 추가해도 같은 결과)."""
    win = lambda p: p.replace("/", "\\")
    if updates:
        shas = [next(sha for name, _, _, sha in items if name == "EBOOT.elf") for items in updates.values()]
        if len(set(shas)) != len(shas):
            raise ValueError("업데이트 EBOOT.elf 해시가 판마다 달라야 판을 구분할 수 있음")
    usage = "사용: apply.bat ^<게임 폴더^> [^<업데이트 폴더^>]" if updates else "사용: apply.bat ^<게임 폴더^>"

    def src(base, rel):
        """원본 경로를 S 에 (.orig 우선)."""
        return [f'set "S={base}\\{win(rel)}"', 'if exist "%S%.orig" set "S=%S%.orig"']

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal",
        f"echo 파이트 나이트 챔피언 한글 패치 {version}",
        f'if "%~1"=="" (echo {usage} & exit /b 1)',
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
        for name, (rel, _) in TARGETS.items():
            if name != "EBOOT.elf":
                lines += src("%G%", rel) + [f'call :check "%S%" {hashes[name]} || exit /b 1']
        lines.append("goto :checked")
    lines.append(":checked")
    if updates:
        lines += [
            'set "U="',
            'if "%~2"=="" (echo 참고: 타이틀 업데이트 1.02 가 설치돼 있으면 업데이트 폴더도 함께 지정해 다시 실행하십시오. & goto :decode)',
            'set "U=%~2"',
            'if not exist "%U%\\EBOOT.elf" (echo 업데이트 폴더에 복호화한 EBOOT.elf 가 없습니다. RPCS3 로 업데이트의 USRDIR\\EBOOT.BIN 을 복호화해 업데이트 폴더에 EBOOT.elf 로 두십시오. & exit /b 1)',
            'call :hash "%U%\\EBOOT.elf" || exit /b 1',
            'set "UR="',
        ]
        for title, items in updates.items():
            elf_sha = next(sha for name, _, _, sha in items if name == "EBOOT.elf")
            lines.append(f'if /i "%H%"=="{elf_sha}" set "UR={title}"')
        lines += [
            "if not defined UR (echo 지원하지 않는 업데이트 EBOOT.elf 입니다. 타이틀 업데이트 1.02 만 지원합니다. & exit /b 1)",
            'if /i not "%UR%"=="%R%" (echo 업데이트 %UR% 와 디스크 %R% 의 판이 다릅니다. & exit /b 1)',
            "goto :ucheck_%R%",
        ]
        for title, items in updates.items():
            lines.append(f":ucheck_{title}")
            for name, rel, _, sha in items:
                if name != "EBOOT.elf":
                    lines += src("%U%", rel) + [f'call :check "%S%" {sha} || exit /b 1']
            lines.append("goto :decode")
    # 디코드: 모든 결과를 *.ko 로 먼저 만든다
    lines.append(":decode")
    for name, (rel, dst) in TARGETS.items():
        lines += [f"echo 적용: {name}"] + src("%G%", rel) + [
            f'"%X%" -d -f -s "%S%" "%P%\\%R%\\{name}.xdelta" "%G%\\{win(dst)}.ko" || (echo 실패: {name} & exit /b 1)']
    if updates:
        lines += ["if not defined U goto :commit", "goto :udecode_%R%"]
        for title, items in updates.items():
            lines.append(f":udecode_{title}")
            for name, rel, dst, _ in items:
                lines += [f"echo 적용: 업데이트 {name}"] + src("%U%", rel) + [
                    f'"%X%" -d -f -s "%S%" "%P%\\%R%\\update\\{name}.xdelta" "%U%\\{win(dst)}.ko" || (echo 실패: 업데이트 {name} & exit /b 1)']
            lines.append("goto :commit")
    # 확정: .ko 를 제자리로 (원본은 처음 한 번만 .orig 로)
    lines.append(":commit")
    for _, (_, dst) in TARGETS.items():
        d = win(dst)
        lines += [f'if not exist "%G%\\{d}.orig" move "%G%\\{d}" "%G%\\{d}.orig" >nul',
                  f'move /y "%G%\\{d}.ko" "%G%\\{d}" >nul']
    lines.append("echo 자막 파일 만들기")
    for fre, eng in subs:
        lines.append(f'copy /y "%G%\\{win(fre)}" "%G%\\{win(eng)}" >nul')
    if updates:
        lines += ["if not defined U goto :finish", "goto :ucommit_%R%"]
        for title, items in updates.items():
            lines.append(f":ucommit_{title}")
            for _, _, dst, _ in items:
                d = win(dst)
                lines += [f'if not exist "%U%\\{d}.orig" move "%U%\\{d}" "%U%\\{d}.orig" >nul',
                          f'move /y "%U%\\{d}.ko" "%U%\\{d}" >nul']
            lines.append("goto :finish")
        lines.append(":finish")
    lines += [
        "echo 완료. 원본은 *.orig 로 남겨 두었습니다.",
        "exit /b 0",
        "",
        ":hash",
        'if not exist "%~1" (echo 파일 없음: "%~1" & exit /b 1)',
        'set "H="',
        "for /f \"skip=1 delims=\" %%h in ('certutil -hashfile \"%~1\" SHA256') do if not defined H set \"H=%%h\"",
        'set "H=%H: =%"',
        "exit /b 0",
        "",
        ":check",
        'call :hash "%~1" || exit /b 1',
        'if /i not "%H%"=="%~2" (echo 원본이 다름: "%~1" & exit /b 1)',
        "exit /b 0",
    ]
    return "\r\n".join(lines) + "\r\n"


README = """파이트 나이트 챔피언 (PS3) 한글 패치 {version}

비공식 팬 번역입니다. Electronic Arts 와 무관합니다. 게임 데이터는 들어 있지 않습니다.

[지원 디스크]
- 일본판 BLJM60267 (게임 버전 01.00)
- 북미판 BLUS30608 (게임 버전 01.00)
- 두 판의 타이틀 업데이트 1.02 (RPCS3 에 설치된 경우)
apply.bat 이 EBOOT 로 판을 알아내 맞는 패치를 적용합니다.

[준비]
1. 정품 디스크에서 게임 폴더를 추출합니다 (PS3_GAME 폴더가 들어 있는 폴더).
2. RPCS3 의 "도구 > SELF 복호화"(또는 rpcs3.exe --decrypt) 로 PS3_GAME\\USRDIR\\EBOOT.BIN 을 복호화하고,
   결과 EBOOT.elf 를 게임 폴더(PS3_GAME 옆)에 둡니다.
3. (업데이트 1.02 를 설치했다면) RPCS3 게임 목록의 버전이 01.02 로 보입니다. 업데이트 폴더는
   RPCS3 폴더의 dev_hdd0\\game\\BLJM60267 (또는 BLUS30608) 입니다. 그 안의 USRDIR\\EBOOT.BIN 도
   같은 방법으로 복호화해, 결과 EBOOT.elf 를 업데이트 폴더(USRDIR 옆)에 둡니다.

[적용]
  업데이트 없이:  apply.bat "게임 폴더 경로"
  업데이트 1.02:  apply.bat "게임 폴더 경로" "업데이트 폴더 경로"

  원본 파일이 맞는지 SHA-256 으로 모두 확인한 뒤에야 파일을 바꿉니다.
  게임 폴더의 boot.big, fe.big, EBOOT 를 바꾸고 영어 자막 파일을 만들며,
  업데이트 폴더를 주면 업데이트의 EBOOT 와 DLC 데이터(dlc_main.big, dlc.toc)도 바꿉니다.
  바뀐 원본은 같은 자리에 *.orig 로 남습니다.

[주의]
- 패치된 EBOOT.BIN 과 DLC 파일은 RPCS3 전용입니다(실기 서명 없음).
- 업데이트 1.02 를 설치해 두고 업데이트 폴더 없이 적용하면 업데이트의 EBOOT 와 DLC 데이터가 우선이라
  자막이 나오지 않고 화면 일부가 영어로 돌아갑니다. 반드시 업데이트 폴더도 함께 지정하십시오.
- PS3 시스템 언어가 한국어/일본어/영어일 때 한글로 나옵니다(게임이 영어 데이터를 씀).
- 한글 글꼴: 나눔고딕 Bold, Black Han Sans (SIL Open Font License 1.1).
- xdelta3 3.1.0: GNU GPL v2 (xdelta3-COPYING.txt). 대응 소스 xdelta3-3.1.0.tar.gz 를 함께 넣었습니다.
"""


def _diff(xdelta, src, new, diff, label):
    """xdelta 차분을 만들고, 다시 적용해 같은 파일이 나오는지 확인."""
    diff.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(xdelta), "-e", "-9", "-S", "djw", "-f", "-s", str(src), str(new), str(diff)], check=True)
    chk = diff.with_suffix(".chk")
    subprocess.run([str(xdelta), "-d", "-f", "-s", str(src), str(diff), str(chk)], check=True)
    if sha256(chk) != sha256(new):
        raise RuntimeError(f"{label}: 차분 검증 실패")
    chk.unlink()
    print(f"{label}.xdelta  {diff.stat().st_size:,} B")


def _assert_current(files, root, label):
    """build/ 의 산출물이 지금 번역·코드로 다시 만든 것과 같은지 (오래된 빌드를 배포하지 않게)."""
    stale = [rel for rel, data in files.items()
             if not (Path(root) / rel).exists() or sha256(Path(root) / rel) != hashlib.sha256(data).hexdigest()]
    if stale:
        raise ValueError(f"{label}: 빌드 결과가 최신이 아님 {stale} — build.py 를 다시 실행하십시오")


def package(version, out_root, xdelta=XDELTA, xdelta_exe=XDELTA_EXE, xdelta_src=XDELTA_SRC, regions=None,
            translations=ROOT / "translations" / "ko", font=build.DEFAULT_HANGUL_FONT):
    regions = regions or REGIONS
    tr = build.load_translations(translations)
    out = Path(out_root) / f"FNC_Korean_{version}"
    if out.exists():
        shutil.rmtree(out)
    hashes, subs_by_region, updates = {}, {}, {}
    for title, r in regions.items():
        extract, elf, game = (ROOT / r["extract"]), (ROOT / r["elf"]), (ROOT / r["game"])
        if build.title_id(extract) != title or build.title_id(game) != title:
            raise ValueError(f"{title}: 추출본/빌드 결과의 타이틀 ID 가 다름")
        extra = build.update_dlc_ids(ROOT / r["update"]) if r.get("update") else set()
        disc = build.build_files(extract, tr, font, extra)
        disc[build.EBOOT] = build.build_eboot(elf, extract)
        _assert_current(disc, game, title)
        if r.get("update"):
            _assert_current(build.build_update(ROOT / r["update"], ROOT / r["update_elf"], tr),
                            ROOT / r["update_game"], f"{title} 업데이트")
        (out / "patch" / title).mkdir(parents=True)
        srcs = {"boot.big": extract / build.BOOT_BIG, "fe.big": extract / build.FE_BIG, "EBOOT.elf": elf}
        hashes[title] = {}
        for name, (_, dst) in TARGETS.items():
            hashes[title][name] = sha256(srcs[name])
            _diff(xdelta, srcs[name], game / dst, out / "patch" / title / f"{name}.xdelta", f"{title}/{name}")
        if r.get("update"):
            upd, upd_game = ROOT / r["update"], ROOT / r["update_game"]
            if not upd_game.exists():
                raise FileNotFoundError(f"{title}: 업데이트 빌드 결과 없음 {upd_game} (build.py --update)")
            updates[title] = []
            for name, src, dst in update_targets(upd):
                src_path = ROOT / r["update_elf"] if name == "EBOOT.elf" else upd / src
                updates[title].append((name, src, dst, sha256(src_path)))
                _diff(xdelta, src_path, upd_game / dst, out / "patch" / title / "update" / f"{name}.xdelta",
                      f"{title}/update/{name}")
        fmv = extract / build.FMV_DIR
        subs_by_region[title] = [(f"{build.FMV_DIR}/{f.name}", f"{build.FMV_DIR}/{f.name[:-len('_fre.sub')]}_eng.sub")
                                 for f in sorted(fmv.glob("*_fre.sub"))]
    subs = next(iter(subs_by_region.values()))
    if any(s != subs for s in subs_by_region.values()):
        raise ValueError("판마다 자막 파일 구성이 다름 — 배치 하나로 처리할 수 없음")
    if updates and set(updates) != set(hashes):
        raise ValueError("업데이트 패치는 모든 판에 있어야 함")
    (out / "apply.bat").write_bytes(bat(version, hashes, subs, updates or None).encode("utf-8"))
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
