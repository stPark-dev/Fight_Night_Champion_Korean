# 초기 조사 — Fight Night Champion (PS3, Japan)

조사일: 2026-10-21. 모든 사실은 아래 원본 리비전에서 직접 확인한 것.

## 원본

| 항목 | 값 |
|---|---|
| 원본 | `Fight Night Champion (Japan).7z` → `Fight Night Champion (Japan).iso` (5,979,242,496 B) |
| 플랫폼 | PS3 BD (UDF 2.50, VolumeId `PS3VOLUME`) |
| 타이틀 ID | **BLJM60267**, TITLE `FIGHT NIGHT CHAMPION`, VERSION 01.01, APP_VER 01.00, PS3_SYSTEM_VER 3.56 |
| 암호화 | ISO는 복호화 상태 (파일 헤더 평문 확인) |
| EBOOT.BIN | `SCE\0` 암호화 SELF (24.7 MB) — 코드 수정 시 복호화 필요. 현재 계획상 불필요 |

일본판이지만 **일본어 텍스트가 없다**. 로컬라이즈 DB는 eng/fre/ger/lng(혼합 테스트) 4종뿐이며, 게임 텍스트는 영어로 표시되는 것으로 추정(런타임 미확인).

## 텍스트 경로 (확인됨)

```
PS3_GAME/USRDIR/databigs/ps3/boot.big        (EB v3 아카이브)
  └ data/ps3/loc/eng/database/eng_us.db      (chunkzip → T3DB v8)
       └ 테이블 LanguageStrings (GJCv): hashid(int32) / stringid / sourcetext
```

### EB v3 아카이브 (`tools/analysis/eb_probe.py`)
- BE. `EB` + u16 ver=3, u32 count, u16 flags, u8 shift(=4)
- 0x0C names_off, 0x10 names+dirs 크기, 0x14 u8 이름레코드 길이 / u8 디렉터리레코드 길이 / u16 디렉터리 수, 0x1C 전체 크기
- 0x30부터 엔트리 16 B: `offset>>4, 0, size, hash` (해시 정렬), 그 뒤 엔트리당 1 B 플래그(전부 0)
- 이름 레코드: u16 dir index + 이름. 디렉터리 테이블은 16 B 정렬
- boot.big / fe.big / be_gp.big / boot_other.big / shaders.big 모두 파싱 성공. 압축 플래그 전부 0 (개별 파일 단위 압축은 파일 자체 포맷)

### chunkzip (`tools/analysis/chunkzip.py`)
- `chunkzip` + u32 ver=2, u32 원본 크기, u32 청크 크기(0x20000), u32 청크 수, u32 정렬(16)
- 청크: u32 압축길이, u32 타입(1=raw deflate), 페이로드는 16 B 정렬
- 4개 DB 모두 원본 크기와 정확히 일치하게 해제됨

### T3DB (`tools/analysis/t3db_dump.py`)
- `DB\0\x08`, 테이블 1개, 레코드 16 B × 10019, 레코드 시작 0x78
- 문자열 필드: 레코드 값 = 문자열 영역(허프만 트리 시작) 기준 바이트 오프셋, `0xFFFFFFFF` = null
- 허프만 트리: 노드 = BE u16 × 2, `XX00`=내부노드 XX, `00XX`=리프 바이트. 루트 0, MSB 우선, 비트 0=왼쪽
- stringid: 1 B 길이(문자 수) + 허프만 비트열 / sourcetext: BE u16 길이 + 허프만 비트열
- 디코딩 결과 UTF-8. 각 문자열 끝 바이트가 다음 문자열 오프셋과 정확히 일치 → 경계 해석 검증됨

## 물량 (eng_us)

| 접두사 | 문자열 | 문자 |
|---|---:|---:|
| TXT | 5,693 | 170,211 |
| OSDK (온라인/EA 계정) | 2,595 | 82,466 |
| CM (챔피언 모드 컷신 자막) | 682 | 26,426 |
| MESSAGE | 406 | 62,190 |
| 기타 | 643 | ~20,500 |
| **합계** | **10,019** (고유 8,922) | **361,854** |

제어 토큰: `\n` 456, `%1s`/`%1d`… printf 계열, `<0>`~`<3>` 161+, `{c0}`~`{c9}` 색상, `{p0x...}`.

## 폰트 (확인됨)

`fe.big` → `data/ps3/fe/fonts/*.ttf` 8종 (Helvetica Neue 변형 6, Eurostile, Machine) + `trunkfonts/*.ttf` 6종.
**런타임 TrueType 래스터라이즈**(eatext). 현재 cmap은 Latin-1 + 일부 기호만. 한글 글리프 없음.
→ 비트맵 폰트 제작·인코딩 개조 없이, TTF에 한글 글리프를 병합하는 방식이 1순위 가설.

## 미해결 (완료를 좌우하는 순서)

1. **런타임 도달성**: 게임이 실제로 `eng_us.db`를 쓰는지, eatext가 BMP 한글 코드포인트를 cmap에서 찾아 그리는지, 글리프 캐시/메모리가 견디는지 — PoC로만 확인 가능
2. **재패킹 수용**: 크기가 바뀐 DB/폰트로 boot.big·fe.big를 재구성해도 로더가 받아들이는지 (외부 TOC/해시 검사 여부)
3. 런타임 검증 수단 (RPCS3 또는 실기)
4. DB 외 텍스트: fe 화면 파일(`ion_sports07` UI) 내 하드코딩 문자열, 텍스처 그래픽 텍스트, EBOOT 내 문자열 — 미조사
5. 배포 형태 (ISO 재빌드 / 게임 폴더 덮어쓰기 / 차분 패치)
