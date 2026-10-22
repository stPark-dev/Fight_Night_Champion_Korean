# 화면 확인 목록 (번역 1차, 2026-10-21)

## 검수 1회차 (2026-10-21, RPCS3 0.0.42-19819 Windows, 캡처 `work/runlogs/qa_*.png`)

입력·캡처: `tools/hitl/winpad.py` (백그라운드 PostMessage + PrintWindow, 검수 전용 키보드 프로필 `fnc_qa`,
창 모드 설정 `work/rpcs3/config_qa.yml`).

### 정상 확인
- 타이틀(START / 버튼을 누르십시오), 자동 저장 안내, 챔피언 모드 프롤로그 FMV 자막, 게임 오버·힌트
- 메인 메뉴·게임 모드 메뉴(큰 원근 글꼴), 하단 버튼 안내 바
- 바로 시합: 진영 선택, 선수 선택(체급·키/체중/리치 줄·종합), 선수 능력치 창
- 레거시: 서버 미연결 안내, 새 레거시 시작, 환영 화면, 선수 갤러리, 선수 성장(기술 목록 전체), 변경 적용 확인,
  상대 가져오기 안내, 아마추어 토너먼트 소개·대진표·메뉴, 시합 확정 대화상자
- 시합: HUD(라운드 1/3, 스태미나), 라운드 사이 "코너로" 안내
- PS3 시스템 저장 화면의 게임 제공 문자열(부제·설명 한글, PARAM.SFO 바이트 한도 안)

### 고친 것 (다음 빌드부터)
- 레거시 진입 시 `OSDK_SIGNIN_REQUIRED` 영어 대화상자 → OSDK 전체 번역으로 범위 확대 (decisions.md)
- 가상 키보드 키 이름(VK_BACK/CAPS/CLEAR/DONE/ESC/SELECT/SHIFT/SPACE/SPECIALKEYS) 영어 → 번역
- 능력치 항목 어순 통일: `안면 스트레이트`, `안면 오른손 훅`, `안면 오른손 어퍼컷` (바디도 같음)
- `TXT_CHIN` 턱 → 맷집, `TXT_NO_THANKS` 괜찮습니다 → 아니요

### 번역 대상 아님 (확인)
- 선수 이름(MIKE TYSON, M. ALI 등)은 eng_us.db 밖(선수 데이터)에서 옴 → 영문 표시
- 하단 ESPN 티커의 곡명(ROUND OF APPLAUSE 등), PS3 시스템 대화상자(RPCS3 시스템 언어)

### 남은 관찰
- (3회차 해명) 첫 레거시 저장의 `cellSaveDataListSave2` ERROR_PARAM(22)는 게임의 funcStat 이 `OK_LAST_NOCONFIRM`(2)을
  돌려줘서 RPCS3 가 오류로 처리한 것(cellSaveData.cpp `display_callback_result_error_message` 기본 분기).
  게임이 이어서 고정 저장으로 성공하는 정상 흐름이며 번역과 무관
- 첫 레거시 저장에서 `cellSaveDataListSave2` CELL_SAVEDATA_ERROR_PARAM(22) 후 게임이 고정 저장으로 재시도해 성공.
  저장 문자열 길이는 한도 안이라 번역 원인은 아닌 것으로 보임. 영어 원본에서도 같은지 비교 필요
- ~~아마추어 토너먼트 소개문 말투~~ → 2회차에서 반말로 수정
- 가상 키보드 `대문자 고정`, `모두 지우기` 칸 폭 확인 필요 (다음 빌드)
- 선수 성장 L1/R1 탭 전환은 입력이 먹지 않아 다른 탭 미확인

원문만으로는 쓰임새를 알 수 없어 임시로 번역한 항목. RPCS3에서 실제 화면을 보고 확정한다.

## 검수 2회차 (2026-10-22, 캡처 `work/runlogs/qa2_*`, `k/`, `k2/`, `o/`, `o2/`)

### 1회차 수정 확인
- 레거시 진입 OSDK 로그인 안내 대화상자 한글 표시
- 세이브 목록·불러오기 확인 화면의 한글 부제·설명

### 정상 확인
- 시합 후: 심판 채점표(승리 방식 KO), 재대결/인스턴트 리플레이/시합 합계 메뉴, 시합 합계 통계, 경기장 배너
- 레거시 센트럴: 아마추어 토너먼트 시상, 일정 캘린더(범례), 시합 잡기·예약 확인, 대진표, 선수 비교,
  캠프 잡기·예약 확인, 레거시 등급 사다리, 로딩 팁

### 고친 것 (다음 빌드부터)
- `TXT_END` 끝 → 지구력 (캠프의 운동 능력 약어 END = Endurance), `TXT_CON`/`TXT_TUF` 영어 → 컨디션/내구력,
  `TXT_SPD` 속도 → 스피드
- 토너먼트 단계 이름 통일: 2회전 상단/하단, 준결승 상단/하단 (1회전과 같은 형식)
- 시합 합계 `R 어퍼` → 오른손 어퍼 (`TXT_R_UPPER`, `TXT_R_UPPERCUT`)
- 아마추어 토너먼트 소개문 합쇼체 → 트레이너 반말

### 코드 수정이 필요한 것 (번역으로 해결 불가)
- 날짜 어순: 캘린더 `1월 2011`, 시합 날짜 `2월 02, 2011` — 월 이름(DB) + 일·연도를 게임 코드가 영어 순서로 조합
  - 시합 날짜 등(`2월 02, 2011`): EBOOT `0x3812ec` 날짜 함수의 영어 분기 → `DATE_PATCHES`로 `2011년 2월 2일`/`2월 2일` (3회차 확인 예정)
  - 캘린더 머리글(`1월 2011`): `legacycentral.big` 의 APT(EA Flash 계열) 스크립트가 `CALENDAR_MONTHS_LONG[월] + 연도`로 조합.
    APT 바이트코드 수정 도구가 필요해 보류(뜻은 통함)

### 시합 중 멈춤 (조사 중)
- 증상: 시합 중 시계가 멈추고 화면은 30fps로 계속 그려짐(게임 시뮬레이션만 정지). 치명 오류 로그 없음
- 1차: RPCS3 GDB 서버(127.0.0.1:2345)에 외부 프로그램이 접속 → GDB 스레드 치명 오류로 에뮬레이션 정지.
  검수 설정에서 GDB 서버를 끔(`work/rpcs3/config_qa.yml`)
- 2차(GDB 꺼짐 상태): 한글판 아마추어 토너먼트 2회전(레이시 전) 1R 1:45에서 정지 (`work/rpcs3/RPCS3_freeze2.log`)
- 비교: 원본 — 바로 시합 8분, 아마추어 15분(2시합) 정지 없음. 한글판 — 바로 시합 8분, 아마추어 15분 정지 없음
- 현재 집계(아마추어): 한글판 5회 중 2회 정지(1회는 GDB), 원본 3회 중 0회. 재현율이 낮아 원인 미확정
- 다음: 재현되면 `tools/build.py --parts` 로 폰트만/DB만 원본으로 되돌린 빌드로 격리 시험

## 검수 3회차 (2026-10-22, 캡처 `work/runlogs/nl/`, `d/`, `soak1/`)

### 2회차 수정 확인
- 선수 성장 기술 목록 어순(안면 스트레이트, 바디 오른손 어퍼컷 …)과 `맷집`
- 가상 키보드 전체 한글(지우기/취소/대문자 고정/Shift/띄어쓰기/완료/특수 문자/모두 지우기), 키 칸 안에 들어감
- 아마추어 토너먼트 소개문 트레이너 반말
- **날짜 EBOOT 패치**: 시합 잡기 화면 `2011년 2월 23일` (이전 `2월 02, 2011`)

### 정상 확인
- 메시지 센터 목록·상세(발신/제목/날짜/본문, 스파링 초대 수락/나가기)
- 레거시 센트럴 메인(내 경력, 순위·P4P 순위·현금·XP, 레거시 등급 사다리, 메뉴 팁)

### 남은 것
- 메시지 날짜 `01/01/2011`(숫자형): 날짜 함수 표에 없는 형식 → 다른 경로. 한국식 `2011.01.01` 여부는 추가 조사
- 캘린더 머리글 `1월 2011`: APT 스크립트(보류)

### 시합 중 멈춤 — 추가 표본
- 2차 멈춤 로그(`work/rpcs3/RPCS3_freeze2.log`)에는 GDB 접속 없음 → 디버거와 무관한 실제 정지
- 3회차: 한글판 새 레거시 아마추어 토너먼트 3시합(약 13분) 정지 없음
- 교대 반복 시험 결과와 분석: [`freeze_investigation.md`](freeze_investigation.md)

## 그림 글자 목록 (2026-10-22, `work/img/sheet__*.png`)

fe.big 의 중첩 BIGF(RefPack 압축, DXT5 DDS) 텍스처를 전부 풀어 확인.

| 대상 | 위치 | 처리 |
|---|---|---|
| 진영 선택 `SELECT SIDES` | `game/screens/playnow/01_boxerselect.big` 항목 4 | **한글 그림으로 교체** (`assets/images/`, `tools/art/select_sides.py`) — 화면 확인 예정 |
| 진영 선택 `VS` | 같은 파일 항목 7 | 유지 |
| 게임 설명서(메인 메뉴 □) | `artassets/manual_ps3/*_eng_*` 25쪽 | 미착수 — 쪽마다 글자 이미지라 다시 그려야 함 |
| 경기장·체육관 로고(`venue_title*`), ESPN/EA/PPV 로고 | `artassets/venue_title*`, overlays | 브랜드·고유명 로고로 유지 |
| 부팅 법적 고지·ESRB | `game/screens/bootflow/*` | 유지 |
| HUD·선수 성장·훈련 아이콘 | overlays, `artassets/boxer_growth` | 글자 없음(버튼 글자 R/LS 등만) |

## 쓰임새 불명 (임시 번역 또는 미번역)

| ID | 원문 | 현재 | 확인할 것 |
|---|---|---|---|
| TXT_CHN, TXT_CON, TXT_CRI, TXT_D, TXT_L, TXT_SFB, TXT_STM | 약어 | 원문 유지 | 능력치 약어(Chin/Conditioning…)인지, 칸 폭 |
| TXT_ICE, TXT_WATER, TXT_OF_THE | "Of Ice", "Of Water", "Of The" | 얼음 / 물 / 원문 | 별명·이름 조합용 조각인지 |
| TXT_BY, TXT_BY_RESULT | "By", "%1s BY %2s" | 제작 / `%2s %1s` | 결과 표시(KO 승) 어순 |
| TXT_OPEN | OPEN | 열기 | 체육관 공개 상태면 "공개" |
| TXT_REC | Rec | 전적 | 녹화(REC)인지 |
| TXT_ROAM, TXT_ROOM | Roam, Room | 이동 / 방 | 카메라·로비 맥락 |
| TXT_DEFAULT | SWING | 스윙 | |
| TXT_CURRENT_GMS | GMs | 현재 GM | |
| TXT_LONG_HEAL_DAMAGE | | 오래 남는 피해 | |
| TXT_WIN_VS | Win Vs | 상대별 승 | |
| TXT_TALE, TXT_TAPE | | 비교 / 테이프 | Tale of the Tape 분할인지 |
| TXT_THE_DUKE | THE DUKE | 더 듀크 | 별명인지 장소인지 |
| TXT_FIGHT_SIM_* | %PUNCHER, %HAND, %PUNCHTYPE, %TARGET | 조사 없는 중계체 | 변수에 들어가는 단어(왼손/안면/바디)와 어순 |
| TXT_PRESS_START_LINE_1/2 | PRESS / START | START / 버튼을 누르십시오 | 두 줄 배치 |
| TXT_WC_ABBR_HW/LW/MW, CLUBSEASON_OWC_* | HW/LW/MW | 원문 유지 | 칸이 넓으면 헤비급/라이트급/미들급 |
| TXT_MS_POINTS, TXT_MSPRICE_CHECK_MARKETPLACE | Xbox 전용 | 번역함 | PS3판 노출 여부 |

## 칸 폭 확인

- `아니요` (SL_No, TXT_NO, TXT_NO_LC, TXT_LC_NO): 원문 "No" 대비 넓음
- `역대 최고` (TXT_TROPHY_10_NAME, 원문 GOAT)
- 체급·통계 약어 칸 전반, 선수 정보 줄(PoC-2에서 잘림 확인)

## 원문 이상 (번역은 원문 ID의 내용대로)

- MESSAGE_TYPE_RUBBER_MATCH_FTW_DRAW 본문과 _SUBJECT 내용이 뒤바뀐 듯
- MESSAGE_TYPE_OPPONENT_CHALLENGE_SUGGESTIONS0/2: 이름 자리에 `%1d %2d` (숫자가 표시될 수 있음)
- CM 화자 오배정 의심: SCENE10_GUS_04, SCENE31_ACE_05, SCENE63_ANDRE_02(거스 말투로 번역), SCENE71_FRANCO_06
- TXT_UNLOCK_ID61: "defeat Raul Castillo Reggie Stewart" → 라울 카스티요만 남김
- ID와 내용 불일치 다수(TXT_L_UPPERCUTS_THROWN = LANDED, TXT_SIG_PUNCH_TRIPLE_JAB = Shuffle Straight 등): 내용을 따름
