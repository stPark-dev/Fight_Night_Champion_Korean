# 화면 확인 목록 (번역 1차, 2026-10-21)

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
