# PoC 기록

## PoC-1: 타이틀 화면 한글 표시 (2026-10-21) — 성공

- 입력: `translations/poc.json` (`TXT_PRESS_START_LINE_1` = "START 버튼을", `TXT_PRESS_START_LINE_2` = "누르세요")
- 폰트: NanumGothicBold(OFL)에서 해당 9자를 `fe.big` UI 폰트 8종에 병합 (`tools/fnc/fontmerge.py`, 캡하이트×1.1)
- 빌드: `python3 tools/build.py translations/poc.json` → `build/game` (boot.big 2,103,264 B 크기 동일·제자리 교체 / fe.big 236,967,648 B, 폰트는 끝에 추가)
  - boot.big sha256 494bb495…9d41, fe.big sha256 b1aaf3f6…25bb
- 런타임: RPCS3 0.0.43-20355, FW 3.56, 창모드. 캡처 `work/runlogs/poc1.png`, `poc1_crops.png`

### 확인된 것
1. 게임은 `eng_us.db`를 사용한다 (타이틀 문구 교체가 반영됨)
2. eatext 렌더러가 TTF cmap의 BMP 한글 코드포인트를 찾아 그린다. 영문·한글 혼합 줄 정상
3. 크기가 바뀐 DB(새 허프만 트리·CRC 재계산)와, 파일이 끝으로 이동·확장된 fe.big을 로더가 받아들인다 (외부 TOC 검사 없음)

### 남은 관찰
- 한글 획이 영문(Helvetica Neue Con Bold)보다 가늘어 보임 → 굵기 맞춤 폰트 선택 필요 (제품 결정 사항)
- 글리프 수가 수천 자로 늘 때의 메모리·글리프 캐시 한계는 미확인 → 전체 문자 세트 PoC 필요
- 화면 파일 하드코딩 문자열·그래픽 텍스트 범위 미조사

## PoC-2: 전체 문자 세트 스트레스 (2026-10-21) — 통과(메뉴 범위)

- 입력: `python3 tools/pseudoloc.py translations/stress.json` → 오프라인 7,388 문자열 = 원문 + KS X 1001 한글 음절(전역 순환, 2,350자 전부 사용)
- 폰트: UI 8종 각각 2,605 글리프, 약 0.86 MB (원본 55–90 KB)
- DB: 2,815,776 B 로 커져 boot.big 끝으로 이동. boot.big sha256 572cec5a…4fb0, fe.big sha256 6d09801c…734b
- 진행 경로(캡처 `work/runlogs/stress_*.png`): 타이틀 → 자동저장 안내 대화상자 → (무입력으로 진행된 감옥 시합) GAME OVER/HINT 화면 → 메인 메뉴 → FIGHT NOW → 진영 선택 → 선수 선택
- 입력 자동화: `tools/hitl/pad.py` (XTest, RPCS3 기본 키보드 패드: Return=START, x=✕, 방향키)

### 확인된 것
1. 2,350자 전부 넣은 폰트 8종 + 커진 DB로 부팅·메뉴 이동에 문제 없음 (치명 오류 로그 없음, 30fps 유지)
2. 한 대화상자에 서로 다른 한글 약 120자 동시 렌더링 정상 → 글리프 캐시 한계에 걸리지 않음(이 화면 기준)
3. 공백 없는 한글 문자열도 자동 줄바꿈됨
4. 메뉴 대형 폰트(원근 변형 포함), 하단 버튼 안내, printf 합성 문자열(`HT %s` 등) 모두 정상

### 새로 드러난 것
- 그래픽 텍스트: 진영 선택 배경 "SELECT SIDES", 하단 바 "User"/ESPN 로고 등은 이미지 — 별도 목록화 필요
- 칸 폭 고정 UI: 긴 문자열은 잘림(선수 정보 줄) → 번역 길이 제약을 화면별로 확인해야 함
- `boot_other.big`의 `data/common/trunkfonts/*.ttf` 6종: 트렁크(복싱 바지) 이름 각인용으로 추정. 사용자 입력 이름과 연결되면 범위 결정 필요
- 시합 중 HUD·챔피언 모드 컷신 자막은 아직 미확인

## PoC-3: 챔피언 모드 컷신 자막·시합 화면 (2026-10-21)

캡처: `work/runlogs/seq7_*.png`(영어), `work/runlogs/fseq_*.png`(프랑스어 시스템 언어)

### 확인된 것
1. 게임 언어 = PS3 시스템 언어. 프랑스어로 바꾸면 `fre_fr.db` 사용. 미지원 언어는 영어로 폴백 (EBOOT 문자열 "Unrecognized Language 0x%x, defaulting to CONSOLE_LANGUAGE_ENGLISH"). 한국어/일본어 PS3 → `eng_us.db` → 현재 패치 경로가 맞음
2. 챔피언 모드 컷신은 FMV(`data/common/fmv/mm_*.vp6`, 영어 음성 내장). 자막은 `mm_*_fre.sub`/`_ger.sub`만 존재
   - `.sub` = `ST00` 레코드 연속: 시작/끝 시각, 표시 영역(320,600,640,120), 색, **DB 문자열 ID(UTF-16LE, 예 `CM_MM_1_SCENE01_GUS_02`)**
   - 프랑스어: 자막 표시됨(대사 + "ELECTRONIC ARTS PRÉSENTE" 크레딧 자막). 영어: 자막 없음, `_eng.sub` 열기 시도조차 없음
   - 즉 CM_ 682 문자열(26,426자)은 **영어 경로에서는 화면에 나오지 않는다**
3. 자막 렌더러는 FE 스크립트 `bootflowmovieplayer.big`(subTitleFileName/subTitleHeaderId)이고, 파일명·언어 결정은 EBOOT 코드(`%s_%s`, `_MovieSubtitleFilePath`). EBOOT는 RPCS3 `--decrypt`로 `work/eboot/EBOOT.elf` 복호화 완료
4. 시합 화면: 다운 카운트 숫자·스틱 안내는 그래픽. GAME OVER/HINT/난이도 메뉴는 DB(한글 정상)
5. PS3 시스템 저장 화면은 게임이 넘긴 DB 문자열을 시스템 폰트로 그림 → 한글 정상
6. 이름 입력(저장 이름): 기본값 "Champion Mode N …"이 DB 문자열에서 옴 → 번역 시 한글이 사용자 입력값(저장 제목)에 들어감. 이번 시험에서 저장은 됨. 바이트 길이 한도는 미확인. 키보드 배열은 언어별(영어 QWERTY / 프랑스어 AZERTY+악센트)
7. 입력 자동화: Qt 창은 `_NET_ACTIVE_WINDOW` 활성화가 필요(`tools/hitl/pad.py` 반영). 장면 전환 직후 첫 입력은 무시될 수 있음

## PoC-4: 영어 경로 FMV 자막 활성화 (EBOOT 패치) (2026-10-21) — 성공

결정: docs/decisions.md (A안). 분석 도구 `tools/analysis/ppc_xref.py` (SNC는 주소 계산에 `lis`+`addic` 사용 — `addi` 아님).

### 원인
- 언어 전역 `*(u32*)0x1725ccc` (0=영어, 1=프랑스어, 2=독일어)
- `0x28cc0c` 자막 언어 접미사 함수: 1→"fre", 2→"ger", 그 외→NULL. NULL이면 자막 파일을 찾지 않음 (챔피언 모드 `mm_*` 경로)
- `0x28a2b4~` 부트플로/어트랙트 영상 플레이어: 같은 분기를 인라인으로 가지며 영어는 `li r30,0`

### 패치 (`tools/fnc/eboot.py` SUBTITLE_PATCHES, 원래 값 검증 후 적용)
1. `0x28a2fc` `li r30,0` → `nop` (r30="eng" 유지)
2. `0x28cc0c` 함수 17워드 재작성: 1→fre, 2→ger, 그 외→**"eng"** (0x12c59ac). 프랑스어·독일어 동작 불변
- 자막 데이터: `mm_*_fre.sub` 36개를 `*_eng.sub`로 복제 (`build.english_subtitles`). ID는 언어 공통이고, 문자열은 현재 언어 DB(eng_us = 한글)에서 조회됨
- 출력 EBOOT는 복호화 ELF 그대로(RPCS3는 ELF 실행 가능). 실기 배포용 서명(fself)은 미해결

### 확인 (RPCS3, 캡처 `work/runlogs/subseq6_*.png`, `sub_zoom.png`)
- 로그: `attract_movie_eng.sub`, `mm_1_eng.sub` 열림
- 챔피언 모드 프롤로그 FMV에 `eng_us.db` 문자열(스트레스 한글 포함) 자막 표시, 크레딧 자막("ELECTRONIC ARTS PRESENTS …")도 표시

### 남은 것
- ~~`0xfc88a4~` 세 번째 언어 분기~~ → 처리함(아래 PoC-4b)
- `0x521cb8` "fre" 무조건 참조 — 용도 미확인
- 자막 타이밍은 프랑스어 기준. 한국어 줄 길이·표시 영역(640×120) 적합성은 번역 후 확인
- 실기(CFW) 배포: 패치 EBOOT 재서명 방법 결정 필요

## PoC-4b: 세 번째 자막 분기 (2026-10-21)

- `0xfc8678` 함수: OPD `0x16bbe70`(함수 포인터)로만 호출되며 UI에 `PlayMovie` 메시지(`_global`)를 보내는 범용 동영상 재생 함수. 영어/기타 언어에서 자막 인자 `r30 = r29`(0으로 초기화됨) → 자막 없음
- UI 스크립트 중 `PlayMovie` 호출은 디버그 `movietest.big`뿐 → 정식 경로 사용 여부는 런타임 미확인
- 패치: `0xfc88c8~0xfc88f8` 13워드 재작성, 영어/기타 → "eng". 프랑스어·독일어 동작 불변
- 안전성: 원본 ELF 전체에서 재작성 블록 내부로 들어오는 외부 분기 없음(테스트 `test_no_external_branch_into_rewritten_blocks`)
- 자막이 원래 없는 영상(`intro`, `boot_movie_*`, `transition`, `fn4_main_menu_transition_ntsc`, `mm_67a`, `mm_97~99`): 이번 실행에서 `_eng.sub` 열기 시도·실패 로그 없음. `mm_67a`/`mm_97~99`는 프랑스어판도 자막 없음(동일 조건)
- 회귀: 세 패치 적용 빌드로 챔피언 모드 프롤로그 자막 정상 (`work/runlogs/subseq10.png`)

## PoC-5: 북미판 BLUS30608 지원 (2026-10-26) — 성공

원본: `Fight Night Champion (USA) (En,Fr).iso` (5,979,242,496 B — 일본판과 같은 크기), BLUS30608, APP_VER 01.00 (일본판 01.01)

### 두 판의 차이 (파일 198개 비교)
- 191개 동일: `boot.big`(번역 DB), 자막 `*.sub`, 영상, 음성 전부 같음
- 다름: `EBOOT.BIN`, `fe.big`, 디스크 식별 파일(SFB/SFO/LIC.DAT/options.viv/PUP)
- `fe.big`: 엔트리 목록 동일, 내용이 다른 것 6개(압축 UI 스크립트 4·설명서 프/독 2 — 일본판 01.01 수정분, 예: ○/× 교체 `A_NoSwap`). 빌드가 바꾸는 34개와 겹치지 않음 → **빌드 결과 34개 엔트리 내용이 두 판에서 바이트 단위로 같음**
- EBOOT: 복호화 ELF 크기는 같으나 코드 세그먼트가 0x100 짧고, 구간별로 주소가 0/-0x10/-0x40/-0xc8/-0xd0/-0x100 등 어긋남 (`tools/analysis/elf_align.py`)

### EBOOT 패치 이식
- 모든 패치 지점의 명령 구조가 두 판에서 같음(나란히 역어셈블 확인). 다른 것은 rodata 주소(문자열 -0xc8 등)와 PlayMovie 함수 위치(-0xc8)뿐
- `tools/fnc/eboot.py`: 주소를 지역 프로필(`Profile`, `PROFILES`)로 분리. 원래 명령 값도 프로필 주소로 다시 만들어 검증. EBOOT 판은 코드 세그먼트 끝으로 자동 식별(`detect_profile`)
- 미국판 주소: `tools/analysis/relocate.py`(주변 바이트 / 즉시값을 가린 명령 패턴 검색)로 찾고, 테스트가 문자열·형식 표·원래 명령으로 검증
- 일본판 결과 EBOOT 는 리팩터링 전과 바이트 단위 동일(테스트 고정)
- `build.py`: 추출본 PARAM.SFO 의 TITLE_ID 와 EBOOT 판이 다르면 빌드 중단

### 런타임 (RPCS3, 캡처 `work/runlogs/us_route2.png`, `us_sub_zoom.png`)
- 타이틀 → 자동저장 안내 → (첫 실행) 프롤로그 FMV → 감옥 시합 → 게임 오버 → 메인 메뉴 → 챔피언 모드 새 게임 → 프롤로그 FMV
- 메뉴·대화상자·저장 이름·난이도 한글, `attract_movie_eng.sub`·`mm_1_eng.sub` 열림, 프롤로그 한글 자막 표시
- 날짜 패치·멈춤 수정 패치는 원래 명령 검증까지만 (미국판 런타임 미확인)

### 미해결
- 배포 패키지(`tools/release.py`)는 아직 일본판 원본 해시 기준 — 미국판용 차분 필요
