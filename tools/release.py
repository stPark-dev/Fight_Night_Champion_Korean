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


EASY_BAT = "한글패치.bat"
_EASY = r"""@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "HERE=%~dp0"
echo 파이트 나이트 챔피언 한글 패치 {version} - 간편 적용
echo.
if not exist "%HERE%apply.bat" goto :nopkg
if not exist "%HERE%xdelta3.exe" goto :nopkg
if not exist "%HERE%patch\" goto :nopkg
tasklist /fi "imagename eq rpcs3.exe" 2>nul | "%SystemRoot%\System32\find.exe" /i "rpcs3.exe" >nul && (echo RPCS3 가 실행 중입니다. RPCS3 를 닫은 뒤 다시 실행하십시오. & goto :fail)

rem 1. 게임 폴더 (인자 또는 선택 창)
set "G=%~1"
if "%G%"=="" call :pick "게임 폴더(PS3_GAME 폴더가 들어 있는 폴더)를 고르십시오" G
if "%G%"=="" goto :fail
if "%G:~-1%"=="\" set "G=%G:~0,-1%"
if not exist "%G%\PS3_GAME\PARAM.SFO" (echo 게임 폴더가 아닙니다. PS3_GAME 폴더가 들어 있는 폴더를 고르십시오: "%G%" & goto :fail)

rem 2. RPCS3 폴더 (인자 또는 선택 창)
set "RP=%~2"
if "%RP%"=="" call :pick "RPCS3 폴더(rpcs3.exe 가 있는 폴더)를 고르십시오" RP
if "%RP%"=="" goto :fail
if "%RP:~-1%"=="\" set "RP=%RP:~0,-1%"
if not defined FNC_TEST_DECRYPT if not exist "%RP%\rpcs3.exe" (echo rpcs3.exe 가 없습니다: "%RP%" & goto :fail)

rem 3. 디스크 EBOOT 복호화 후 SHA-256 으로 판(일본/북미)을 정한다 (apply.bat 과 같은 기준)
call :decrypt "%G%\PS3_GAME\USRDIR\EBOOT.BIN" "%G%\EBOOT.elf" || goto :fail
call :hash "%G%\EBOOT.elf"
set "T="
{regions}
if not defined T (echo 지원하지 않는 디스크입니다. 지원: {titles} 게임 버전 01.00 & goto :fail)
echo 디스크: %T%

rem 4. 그 판의 업데이트가 RPCS3 dev_hdd0 에 있으면 1.02 인지 EBOOT.BIN 크기(13370336 바이트)로 확인
call :hdd0
call :update || goto :fail
set "HASU="
if defined U set "HASU=1"
if defined HASU (echo 업데이트 1.02: 있음 - 함께 패치합니다 "%U%") else (echo 업데이트 1.02: 없음)
if defined HASU call :decrypt "%U%\USRDIR\EBOOT.BIN" "%U%\EBOOT.elf" || goto :fail

rem 5. 적용 (해시 확인 후)
echo.
if defined HASU (call "%HERE%apply.bat" "%G%" "%U%") else (call "%HERE%apply.bat" "%G%")
if errorlevel 1 goto :fail
echo.
echo 끝났습니다. RPCS3 에서 게임을 실행하십시오. (Console Language 는 기본값 English 그대로 두면 됩니다)
echo 첫 실행은 RPCS3 가 셰이더를 만드느라 몇 분 동안 진행 막대만 보입니다. 끄지 말고 기다리십시오.
if not defined HASU (
  echo.
  echo [주의] 업데이트 1.02 없이 패치했습니다.
  echo        나중에 1.02 를 설치하면 자막 등 일부가 영어로 돌아갑니다. 그때 이 파일을 한 번 더 실행하십시오.
)
pause
exit /b 0

:nopkg
echo 패치 파일이 옆에 없습니다. 받은 zip 의 압축을 모두 푼 뒤, 푼 폴더에서 이 파일을 실행하십시오.
:fail
echo.
echo 중단했습니다. 위 메시지를 확인하십시오. 게임 파일은 확인 단계에서 멈췄다면 바뀌지 않았습니다.
pause
exit /b 1

:pick
rem %1 안내문, %2 결과 변수. 선택 창(PowerShell, 맨 앞에 띄움)이 안 되면 직접 입력.
set "%~2="
set "FNC_DESC=%~1"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -STA -Command "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false; Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.Form; $f.TopMost=$true; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description=$env:FNC_DESC; if($d.ShowDialog($f) -eq 'OK'){{$d.SelectedPath}}" 2^>nul`) do set "%~2=%%P"
if defined %~2 exit /b 0
echo %~1
set /p "%~2=경로를 입력하십시오: "
if defined %~2 call set "%~2=%%%~2:"=%%"
exit /b 0

:update
rem U = 디스크 판의 업데이트 폴더. 없으면 비우고 성공, 1.02 가 아니면 실패. 이미 패치했다면 EBOOT.BIN.orig 가 원본.
set "U=%HDD0%\game\%T%"
set "EB=%U%\USRDIR\EBOOT.BIN"
if exist "%EB%.orig" set "EB=%EB%.orig"
if not exist "%EB%" (set "U=" & exit /b 0)
for %%A in ("%EB%") do set "EBZ=%%~zA"
if "%EBZ%"=="13370336" exit /b 0
echo 설치된 업데이트가 1.02 가 아닙니다: "%U%"
echo 이 패치는 업데이트 1.02 만 지원합니다. RPCS3 로 1.02 를 설치한 뒤 다시 실행하십시오.
set "U="
exit /b 1

:hdd0
rem RPCS3 config\vfs.yml (옛 버전은 RPCS3 폴더) 의 /dev_hdd0/ 경로. 없으면 기본값 RPCS3\dev_hdd0
rem for 변수는 다시 펼쳐지지 않으므로 따옴표·%·^ 가 든 값도 그대로 읽힌다.
set "HDD0=%RP%\dev_hdd0"
set "VFS=%RP%\config\vfs.yml"
if not exist "%VFS%" set "VFS=%RP%\vfs.yml"
if not exist "%VFS%" exit /b 0
set "EMU="
set "V="
for /f "usebackq tokens=1,*" %%A in ("%VFS%") do (
  if "%%A"=="$(EmulatorDir):" set "EMU=%%B"
  if "%%A"=="/dev_hdd0/:" set "V=%%B"
)
if not defined V exit /b 0
if defined EMU set "EMU=%EMU:"=%"
if not defined EMU set "EMU=%RP%\"
set "V=%V:"=%"
if "%V:~0,14%"=="$(EmulatorDir)" set "V=%EMU%%V:~14%"
set "V=%V:/=\%"
if "%V:~-1%"=="\" set "V=%V:~0,-1%"
set "HDD0=%V%"
exit /b 0

:hash
set "H="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "%~1" SHA256') do if not defined H set "H=%%h"
if defined H set "H=%H: =%"
exit /b 0

:decrypt
rem %1 암호화된 EBOOT.BIN, %2 결과 EBOOT.elf. 이미 패치했다면 *.orig 가 원본.
rem 남아 있던 EBOOT.elf 가 깨졌을 수도 있어 매번 다시 복호화한다. 임시 폴더에서 RPCS3 로.
set "SRC=%~1"
if exist "%~1.orig" set "SRC=%~1.orig"
set "TD=%TEMP%\fnc_kr_%RANDOM%%RANDOM%"
mkdir "%TD%" || exit /b 1
copy /y "%SRC%" "%TD%\EBOOT.BIN" >nul || (rd /s /q "%TD%" & exit /b 1)
echo 복호화: "%~1"
if defined FNC_TEST_DECRYPT (call "%FNC_TEST_DECRYPT%" "%TD%\EBOOT.BIN") else (start "" /wait "%RP%\rpcs3.exe" --no-gui --decrypt "%TD%\EBOOT.BIN")
if not exist "%TD%\EBOOT.elf" (echo 복호화에 실패했습니다: "%~1" & rd /s /q "%TD%" & exit /b 1)
copy /y "%TD%\EBOOT.elf" "%~2" >nul || (echo 복호화한 파일을 옮기지 못했습니다: "%~2" & rd /s /q "%TD%" & exit /b 1)
rd /s /q "%TD%"
exit /b 0
"""


def easy_bat(version, disc_elfs):
    """더블클릭용: 폴더 선택 → RPCS3 로 EBOOT 복호화 → 해시로 판 결정 → 그 판의 업데이트 1.02 감지 → apply.bat.
    disc_elfs: {타이틀ID: 복호화한 디스크 EBOOT.elf sha256}."""
    regions = "\n".join(f'if /i "%H%"=="{sha}" set "T={title}"' for title, sha in disc_elfs.items())
    text = (_EASY.replace("{version}", version).replace("{regions}", regions)
            .replace("{titles}", "/".join(disc_elfs)).replace("{{", "{").replace("}}", "}"))
    return text.replace("\n", "\r\n")


README = """파이트 나이트 챔피언 (PS3) 한글 패치 {version}

비공식 팬 번역입니다. Electronic Arts 와 무관합니다. 게임 데이터는 들어 있지 않습니다.

[지원 디스크]
- 일본판 BLJM60267 (게임 버전 01.00)
- 북미판 BLUS30608 (게임 버전 01.00)
- 두 판의 타이틀 업데이트 1.02 (RPCS3 에 설치한 경우)
RPCS3 메뉴는 한국어 번역이 없어 영어 이름으로 적었습니다.

[간편 적용 - 권장]
1. 받은 게임 파일이 .7z 나 .zip 이면 먼저 압축을 풀어 .iso 파일을 꺼냅니다.
2. .iso 파일을 폴더로 풉니다. 빈 공간이 6GB 쯤 필요합니다. (.iso 그대로는 패치할 수 없습니다)
   - 반디집: .iso 파일을 오른쪽 클릭 → 「(파일 이름)\\ 에 풀기」
   - 7-Zip: .iso 파일을 오른쪽 클릭 → 7-Zip → 「"(파일 이름)\\" 에 풀기」
   풀린 폴더 안에 PS3_GAME 폴더가 보이면 됩니다. 이 폴더가 "게임 폴더" 입니다.
3. RPCS3 의 File > Add Games 로 게임 폴더를 추가합니다.
4. 업데이트 1.02 는 꼭 필요하지 않습니다. 쓸 생각이라면 반드시 패치보다 먼저 설치하십시오.
   File > Install Packages/Raps/Edats 로 업데이트 pkg 를 설치하고,
   RPCS3 게임 목록의 버전이 01.02 로 보이면 설치된 것입니다.
5. RPCS3 를 닫고, 이 폴더의 한글패치.bat 을 더블클릭합니다.
   (Windows 보안 경고가 뜨면 「추가 정보」 → 「실행」 을 누르십시오)
   게임 폴더와 RPCS3 폴더(rpcs3.exe 가 있는 폴더)를 차례로 고르면
   RPCS3 로 EBOOT 를 복호화하고, 업데이트 1.02 가 있으면 알아서 함께 패치합니다.
6. RPCS3 에서 게임을 실행합니다. 설정의 Console Language 는 기본값(English) 그대로 두면 됩니다.
   (Korean·Japanese 로 바꿔도 한글로 나옵니다)
   첫 실행은 RPCS3 가 셰이더를 만드느라 몇 분 동안 진행 막대만 보입니다. 멈춘 것이 아니니 기다리십시오.
   타이틀 화면에 「START / 버튼을 누르십시오」가 나오면 성공입니다.
패치한 뒤에 업데이트 1.02 를 설치(또는 다시 설치)했다면 한글패치.bat 을 한 번 더 실행하십시오.

[직접 적용 - apply.bat]
한글패치.bat 이 안 될 때 쓰는 방법입니다.
1. RPCS3 의 Utilities > Decrypt PS3 Binaries 로 게임 폴더의 PS3_GAME\\USRDIR\\EBOOT.BIN 을 복호화합니다.
   EBOOT.elf 가 같은 USRDIR 폴더에 생깁니다. 이것을 게임 폴더 맨 위(PS3_GAME 옆)로 옮깁니다.
2. 업데이트 1.02 를 설치했다면 업데이트 폴더(RPCS3 폴더의 dev_hdd0\\game\\BLJM60267, 북미판은 BLUS30608)의
   USRDIR\\EBOOT.BIN 도 같은 방법으로 복호화하고, 생긴 EBOOT.elf 를 업데이트 폴더 맨 위(USRDIR 옆)로 옮깁니다.
3. 명령 프롬프트에서 실행합니다.
     업데이트 없이:  apply.bat "게임 폴더 경로"
     업데이트 1.02:  apply.bat "게임 폴더 경로" "업데이트 폴더 경로"

[적용 내용]
원본 파일이 맞는지 SHA-256 으로 모두 확인한 뒤에야 파일을 바꿉니다. 하나라도 다르면 아무것도 바꾸지 않습니다.
게임 폴더의 boot.big, fe.big, EBOOT 를 바꾸고 영어 자막 파일 36개를 만들며,
업데이트 1.02 가 있으면 업데이트의 EBOOT 와 DLC 데이터(dlc_main.big, dlc.toc)도 바꿉니다.
바뀐 원본은 같은 자리에 *.orig 로 남습니다. 이미 패치한 폴더에 다시 실행해도 됩니다.

[잘 안 될 때]
- 자막이 안 나오거나 게임 오버 화면부터 영어로 나옴: 업데이트 1.02 가 패치되지 않은 경우입니다. 다시 실행하십시오.
- "원본이 다름": 지원하지 않는 덤프·리비전이거나 *.orig 파일이 바뀐 경우입니다.
- "판이 다릅니다": 게임 폴더와 업데이트 폴더가 서로 다른 판(일본판/북미판)입니다.
- "RPCS3 가 실행 중": RPCS3 를 닫은 뒤 다시 실행하십시오.
- "패치 파일이 옆에 없습니다": zip 을 연 창 안에서 바로 실행한 경우입니다. 압축을 모두 푼 뒤 푼 폴더에서 실행하십시오.
- "설치된 업데이트가 1.02 가 아닙니다": 업데이트는 1.02 만 지원합니다. RPCS3 로 1.02 를 설치한 뒤 다시 실행하십시오.
- 첫 실행에서 진행 막대만 몇 분 보임: RPCS3 가 셰이더를 만드는 중입니다. 두 번째 실행부터는 바로 시작합니다.
- 패드가 안 됨(듀얼센스·듀얼쇼크): Steam 이 패드를 잡고 있으면 RPCS3 가 입력을 못 받는 일이 많습니다.
  Steam 을 완전히 종료하거나 Steam 설정 > 컨트롤러에서 PlayStation 컨트롤러 지원을 끈 뒤, 패드를 다시 꽂으십시오.
  RPCS3 의 Configuration > Pads 에서 버튼을 눌러 화면 그림이 반응하는지 보면 입력이 들어오는지 알 수 있습니다.
- 키보드로 하고 싶음: Configuration > Pads 에서 Player 1(패드도 쓰려면 Player 2)의 Handler 를 Keyboard 로 고르십시오.
  이 게임은 오른쪽 스틱으로 펀치를 날려 시합은 패드가 훨씬 편합니다.

[주의]
- 패치된 EBOOT 와 DLC 파일은 RPCS3 전용입니다(실기 서명 없음).
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
    (out / EASY_BAT).write_bytes(easy_bat(version, {t: h["EBOOT.elf"] for t, h in hashes.items()}).encode("utf-8"))
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


def zip_package(folder):
    """배포 폴더를 같은 이름의 zip 으로. 한글 이름에 UTF-8 표시(zipfile 이 자동)를 남겨 Windows 에서 깨지지 않게."""
    import zipfile
    folder = Path(folder)
    out = folder.parent / f"{folder.name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--out", default=ROOT / "release")
    ap.add_argument("--xdelta", default=XDELTA, help="차분 생성·검증에 쓸 xdelta3 (이 OS 용)")
    ap.add_argument("--xdelta-exe", default=XDELTA_EXE, help="패키지에 넣을 Windows 용 xdelta3.exe")
    ap.add_argument("--xdelta-src", default=XDELTA_SRC, help="xdelta3-3.1.0.tar.gz (GPL 대응 소스)")
    args = ap.parse_args()
    out = package(args.version, args.out, args.xdelta, args.xdelta_exe, args.xdelta_src)
    z = zip_package(out)
    print(out)
    print(f"{z}  {z.stat().st_size:,} B  sha256={sha256(z)}")


if __name__ == "__main__":
    main()
