# Fight Night Champion 한글화 (PS3)

EA SPORTS **Fight Night Champion** PS3의 한국어 팬 번역 프로젝트입니다.
지원 판: 일본판 **BLJM60267** (v01.01), 북미판 **BLUS30608** (v01.00).

> **현재 상태: 1차 번역 완료, 화면 검수 진행 중**
> 문자열 9,983개 중 9,556개를 번역했습니다(나머지는 곡명·브랜드·기호 등 의도적 원문 유지). RPCS3 화면 검수 1회차를 마쳤고, 배포용 패치는 아직입니다.

이 저장소에는 **게임 데이터가 들어 있지 않습니다.** 원본 디스크 이미지·추출 파일·게임 텍스트는 각자 정품에서 준비해야 합니다.

## 진행 상황

| 항목 | 상태 |
|---|---|
| 텍스트 위치·포맷 해석 (EB 아카이브 / chunkzip / T3DB 허프만 DB) | 완료, 원본과 바이트 단위 왕복 검증 |
| 한글 폰트 (TTF 8종에 한글 글리프 병합) | 완료, KS X 1001 2,350자 스트레스 통과 |
| 메뉴·대화상자·시스템 저장 화면 한글 표시 | RPCS3 확인 |
| 챔피언 모드 FMV 자막 (영어 경로에서는 원래 비활성) | EBOOT 패치로 활성화, RPCS3 확인 |
| 번역 | 1차 완료 9,556/9,983 (온라인 OSDK 포함 전체. 오프라인 흐름에도 OSDK 문구가 나와 범위 확대) |
| 화면 검수 (칸 폭·쓰임새 불명 항목) | 1회차 완료(메뉴·레거시 초반·시합 HUD) — [`docs/qa.md`](docs/qa.md) |
| 그림 글자 | 진영 선택 화면·게임 설명서 25쪽 한글화 (경기장·브랜드 로고는 유지) — `assets/` |
| 배포 | xdelta 패치 + `apply.bat` (RPCS3 전용, 실기용 EBOOT 서명 미결정) |

상세 기록: [`docs/survey.md`](docs/survey.md) (초기 조사), [`docs/poc.md`](docs/poc.md) (PoC 1~4), [`docs/decisions.md`](docs/decisions.md) (결정 기록), [`docs/style.md`](docs/style.md)·[`docs/glossary.md`](docs/glossary.md) (번역 규칙·용어집), [`docs/qa.md`](docs/qa.md) (화면 확인 목록)

## 동작 방식

- 게임 언어는 PS3 시스템 언어를 따르며, 한국어·일본어 본체에서는 영어(`eng_us.db`)로 실행됩니다. 이 영어 DB를 한국어로 바꿉니다.
- UI 폰트는 런타임 TrueType 렌더링이므로 기존 TTF에 한글 글리프만 병합합니다(원본 글리프·메트릭 보존).
- 컷신 자막은 원래 프랑스어·독일어에서만 켜집니다. EBOOT의 자막 언어 분기 3곳을 고쳐 영어 경로에서도 `*_eng.sub`(프랑스어 자막 타이밍 복제)를 읽게 하고, 대사는 `eng_us.db`에서 가져옵니다.

## 준비물

- 정품 디스크에서 만든 ISO — 일본판(BLJM60267) 또는 북미판(BLUS30608). 두 판은 데이터가 거의 같고 EBOOT 주소만 달라, 빌드가 EBOOT 판을 자동 식별하고 디스크 타이틀 ID와 다르면 멈춥니다.
- Python 3.11+, `fontTools`, `pytest` / (분석·런타임 검증용) `capstone`, `python-xlib`
- [RPCS3](https://rpcs3.net/) — EBOOT 복호화와 런타임 검증
- 한글 원본 폰트: 나눔고딕 Bold (SIL OFL) — 기본 경로 `/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf`

## 빌드

```bash
# 1) 원본 추출 (저장소에 포함되지 않음)
7z x -owork/extract "Fight Night Champion (Japan).iso"

# 2) EBOOT 복호화
mkdir -p work/eboot && cp work/extract/PS3_GAME/USRDIR/EBOOT.BIN work/eboot/
rpcs3 --no-gui --decrypt "$PWD/work/eboot/EBOOT.BIN"      # → work/eboot/EBOOT.elf

# 3) 테스트
python3 -m venv --system-site-packages .venv && .venv/bin/pip install capstone python-xlib
.venv/bin/python -m pytest -q tests

#    실데이터 테스트는 work/extract, work/eboot/EBOOT.elf, 나눔고딕이 없으면 skip 됩니다(결과의 skipped 수 확인)

# 4) 빌드 → build/game (원본은 하드링크, 변경 파일만 새로 씀)
python3 tools/build.py translations/ko
```

Windows(Git Bash)에서는 7-Zip 대신 Bandizip 콘솔(`bz x -o:work/extract …iso`), `rpcs3.exe --no-gui --decrypt <EBOOT.BIN 전체 경로>`, `python`을 쓰면 됩니다. 나눔고딕 Bold는 `work/fonts/NanumGothic-Bold.ttf`에 두면 우선 사용합니다(Google Fonts `ofl/nanumgothic`).

### 배포 패키지

```bash
python tools/build.py translations/ko                                    # 일본판 → build/game
python tools/build.py translations/ko --extract work/extract_us --elf work/eboot_us/EBOOT.elf --out build/game_us
python tools/release.py v0.1        # → release/FNC_Korean_v0.1/ (두 판 xdelta 차분 약 5.5MB + apply.bat, zip 약 6.4MB)
```

한 패키지에 일본판·북미판 차분이 모두 들어갑니다. `apply.bat`이 복호화한 `EBOOT.elf`의 SHA-256으로 판을 고르고, 그 판의 원본 `boot.big`·`fe.big` 해시를 확인한 뒤 적용합니다(원본은 `*.orig`로 보존, 영어 자막 파일은 프랑스어 자막을 복제해 생성). 패키지에는 게임 데이터가 없습니다.

xdelta3 3.1.0(동봉 `xdelta3.exe`)은 **GPL v2**라 라이선스 전문과 대응 소스(`xdelta3-3.1.0.tar.gz`)를 함께 넣습니다. 준비물: `work/tools/xdelta/`에 [xdelta-gpl v3.1.0](https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0)의 `xdelta3-3.1.0.tar.gz`·`xdelta3-3.1.0-x86_64.exe.zip`(압축 해제), Linux에서는 tarball을 빌드한 `xdelta3-3.1.0/xdelta3`.

### 번역 작업 흐름

```bash
python tools/export_source.py            # 원문 → work/source/<접두사>.json (저장소 밖)
python tools/batches.py                  # 작업 단위 → work/batches/NN_<접두사>.json
#   배치별 번역 결과 → work/out/NN_<접두사>.json  (docs/style.md, docs/glossary.md 기준)
python tools/merge_batches.py            # → translations/ko/<접두사>.json
python tools/check_translations.py       # 토큰·줄바꿈·글자 세트 검사, 진행률
```

빌드 결과물(`build/game`)은 RPCS3에서 디스크 게임 폴더로 실행할 수 있습니다. 출력 EBOOT는 복호화 ELF 그대로라 **현재는 RPCS3 전용**입니다.

`translations/*.json`은 `{ "문자열 ID": "번역문" }` 형식입니다. 시험용 의사 번역은 `python3 tools/pseudoloc.py translations/stress.json`으로 생성합니다(게임 원문을 포함하므로 저장소에 올리지 않음).

## 구성

```
tools/
  build.py            제품 빌드 (원본 → build/game)
  pseudoloc.py        스트레스 시험용 의사 번역 생성
  fnc/
    eb.py             EA 'EB' v3 빅파일 아카이브 읽기/교체
    chunkzip.py       EA chunkzip (청크 raw deflate)
    t3db.py           T3DB v8 로컬라이즈 DB (허프만 문자열, CRC-32/MPEG-2)
    fontmerge.py      게임 TTF에 한글 글리프 병합
    eboot.py          복호화 EBOOT 명령 패치 (원래 값 검증 후 적용)
  analysis/           포맷·코드 분석용 스크립트
  hitl/               RPCS3 입력 자동화·캡처 (런타임 검증 보조)
tests/                단위·통합 테스트
docs/                 조사·PoC·결정 기록
translations/         번역 입력
```

## 북미판 빌드

```bash
7z x -owork/extract_us "Fight Night Champion (USA) (En,Fr).iso"
mkdir -p work/eboot_us && cp work/extract_us/PS3_GAME/USRDIR/EBOOT.BIN work/eboot_us/
rpcs3 --no-gui --decrypt "$PWD/work/eboot_us/EBOOT.BIN"
python3 tools/build.py translations/ko --extract work/extract_us --elf work/eboot_us/EBOOT.elf --out build/game_us
```

## EBOOT 패치 목록

아래 주소는 일본판 기준입니다. 북미판 주소는 `tools/fnc/eboot.py`의 `PROFILES["BLUS30608"]`에 있습니다(PlayMovie 분기 `0xfc8800`, rodata 문자열·형식 칸은 -0xc8 이동, 동굴 `0x16a2bf0`, 나머지 코드 지점은 같은 주소).


| 주소 | 내용 |
|---|---|
| `0x28a2fc` | 부트플로/어트랙트 영상: 영어일 때 자막 접미사 제거(`li r30,0`) → `nop` |
| `0x28cc0c` | 자막 언어 접미사 함수: 영어/기타 → `"eng"` (프랑스어·독일어 불변) |
| `0xfc88c8` | `PlayMovie` 메시지 함수의 같은 분기: 영어/기타 → `"eng"` |
| `0x381820`~`0x381850` | 날짜 함수 영어 분기: 인자 순서 (연도, 월이름, 일) + 한국어 형식 `"%d년 %s %d일"` / `"%s %d일"` |
| `0x12d2ef0`, `0x12d2f08` | 스페인어 날짜 형식 칸(이 게임에서 미사용)을 위 한국어 형식으로 교체 |
| `0x381468`~`0x381488` | 숫자 날짜 영어 분기: `%02d/%02d/%04d` → `%04d.%02d.%02d` (연·월·일) |
| `0x4a5010`, `0x7bc0c8`, `0x7bb96c`, 동굴 `0x16a2cf0` | 리플레이 비동기 쓰기 경쟁 수정(시합 중 멈춤): 일꾼이 완료 기록 전에 바쁨 플래그를 지움. 코드 세그먼트를 빈 공간으로 늘려 동굴 사용 — 20분×12회 검증 완료 |

## 라이선스·고지

- 이 프로젝트는 비공식 팬 번역이며 Electronic Arts와 무관합니다. Fight Night Champion은 Electronic Arts Inc.의 상표·저작물입니다.
- 게임 데이터, 디스크 이미지, 게임 원문 텍스트는 배포하지 않습니다.
- 한글 글리프 원본인 나눔고딕은 SIL Open Font License 1.1을 따릅니다. 자세한 내용은 [`NOTICE`](NOTICE)를 보세요.
