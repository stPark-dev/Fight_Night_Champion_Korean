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
- 첫 레거시 저장에서 `cellSaveDataListSave2` CELL_SAVEDATA_ERROR_PARAM(22) 후 게임이 고정 저장으로 재시도해 성공.
  저장 문자열 길이는 한도 안이라 번역 원인은 아닌 것으로 보임. 영어 원본에서도 같은지 비교 필요
- 아마추어 토너먼트 소개문은 합쇼체로 번역됐는데 내용은 캠프(트레이너) 말투 — 반말로 바꿀지 검토
- 가상 키보드 `대문자 고정`, `모두 지우기` 칸 폭 확인 필요 (다음 빌드)
- 선수 성장 L1/R1 탭 전환은 입력이 먹지 않아 다른 탭 미확인

원문만으로는 쓰임새를 알 수 없어 임시로 번역한 항목. RPCS3에서 실제 화면을 보고 확정한다.

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
