"""복호화된 EBOOT(ELF64 BE)에 명령 단위 패치 적용. 모든 패치는 원래 값 확인 후 적용."""
import re
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Patch:
    vaddr: int
    old: int
    new: int
    why: str


class asm:
    """필요한 PPC 명령만 인코딩."""
    NOP = 0x60000000
    BLR = 0x4E800020

    @staticmethod
    def _d(op, rd, ra, imm):
        return (op << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)

    @classmethod
    def lis(cls, rd, imm):
        return cls._d(15, rd, 0, imm)

    @classmethod
    def addic(cls, rd, ra, imm):
        return cls._d(12, rd, ra, imm)

    @classmethod
    def lwz(cls, rd, disp, ra):
        return cls._d(32, rd, ra, disp)

    @classmethod
    def mr(cls, ra, rs):
        """ori rA, rS, 0 (SNC 가 레지스터 복사에 쓰는 형태)"""
        return cls._d(24, rs, ra, 0)

    @classmethod
    def cmpwi(cls, ra, imm, cr=0):
        return cls._d(11, cr << 2, ra, imm)

    @staticmethod
    def b(at, target):
        li = target - at
        if li & 3 or not -0x2000000 <= li < 0x2000000:
            raise ValueError("b 범위 밖")
        return (18 << 26) | (li & 0x3FFFFFC)

    @staticmethod
    def beq(at, target, cr=0):
        bd = target - at
        if bd & 3 or not -0x8000 <= bd < 0x8000:
            raise ValueError("beq 범위 밖")
        return (16 << 26) | (12 << 21) | ((cr * 4 + 2) << 16) | (bd & 0xFFFC)


def _rewrite(start, old_words, new_words, why):
    if len(new_words) > len(old_words):
        raise ValueError("새 코드가 원래 함수보다 큼")
    new_words = list(new_words) + [asm.NOP] * (len(old_words) - len(new_words))
    return tuple(Patch(start + 4 * i, o, n, why) for i, (o, n) in enumerate(zip(old_words, new_words)))


@dataclass(frozen=True)
class Profile:
    """지역판별 EBOOT 주소. 두 판은 패치 지점의 명령 구조가 같고 주소(주로 rodata)만 다르다.
    미국판 주소는 tools/analysis/relocate.py 로 일본판에서 다시 찾은 값이며 테스트가 문자열·원래 명령으로 검증한다."""
    title: str
    text_end: int            # 코드 세그먼트(첫 PT_LOAD) 끝 = va + filesz
    eng: int                 # 자막 접미사 문자열 "eng"/"fre"/"ger"
    fre: int
    ger: int
    playmovie_cmp: int       # PlayMovie 함수의 `cmpwi r3,1` (그 다음 명령부터 분기 블록)
    date_en_fmt: int         # 영어 날짜 형식 "%s %02d, %04d"
    date_en_fmt_noyear: int  # "%s %02d"
    ko_date_ymd: int         # 한국어 형식으로 덮어쓸 스페인어 형식 칸 "%02d de %s de %04d"
    ko_date_md: int          # "%02d de %s"
    num_date_table: int      # 숫자형 날짜 형식 표 (+0x78 = "%04d.%02d.%02d")
    memcfg_at: int           # 내장 메모리 설정 텍스트 시작
    bootflow_li: int = 0x28A2FC
    suffix_fn: int = 0x28CC0C
    lang: int = 0x1725CCC    # 언어 전역 (u32)
    date_en: int = 0x381820
    date_num: int = 0x381468
    replay_cb: int = 0x4A5010
    replay_cb_opd: int = 0x16C8D60
    worker_done: int = 0x7BC0C8
    cancel_done: int = 0x7BB96C
    worker_job: int = 25     # 일꾼 완료 기록 `stw res,8(job)` 의 레지스터
    worker_res: int = 5

    @property
    def cave(self):
        return self.text_end + 8


PROFILES = {p.title: p for p in (
    Profile("BLJM60267", text_end=0x16A2CE8, eng=0x12C59AC, fre=0x12C8BB0, ger=0x12C59BC,
            playmovie_cmp=0xFC88C0, date_en_fmt=0x12D2ED8, date_en_fmt_noyear=0x12D2EE8,
            ko_date_ymd=0x12D2EF0, ko_date_md=0x12D2F08, num_date_table=0x12D2DC8, memcfg_at=0x12B6D72),
    Profile("BLUS30608", text_end=0x16A2BE8, eng=0x12C58E4, fre=0x12C8AE8, ger=0x12C58F4,
            playmovie_cmp=0xFC87F8, date_en_fmt=0x12D2E10, date_en_fmt_noyear=0x12D2E20,
            ko_date_ymd=0x12D2E28, ko_date_md=0x12D2E40, num_date_table=0x12D2D00, memcfg_at=0x12B6CA2),
    # 타이틀 업데이트 1.02 (BLJM60267_T4 / BLUS30608_T1): 두 판의 EBOOT 코드가 같다(빌드 날짜 문자열 등만 다름).
    # 주소는 relocate.py + 명령 패턴 검색으로 찾았다(docs/poc.md PoC-6). 일꾼 완료 기록 레지스터가 다르다.
    Profile("UPDATE_1.02", text_end=0x16AEDE8, eng=0x12D6908, fre=0x12D9C90, ger=0x12D6918,
            playmovie_cmp=0xFE915C, date_en_fmt=0x12D05DC, date_en_fmt_noyear=0x12D05EC,
            ko_date_ymd=0x12D05F4, ko_date_md=0x12D060C, num_date_table=0x12D04CC, memcfg_at=0x12C2442,
            bootflow_li=0x30EA08, suffix_fn=0x3113D4, lang=0x1724944, date_en=0x241638, date_num=0x241280,
            replay_cb=0x4AC540, replay_cb_opd=0x16C8DE0, worker_done=0x7C3948, cancel_done=0x7C31CC,
            worker_job=23, worker_res=22),  # 두 판(BLJM60267·BLUS30608) 업데이트 공통
)}
JP = PROFILES["BLJM60267"]
ENG, FRE, GER = JP.eng, JP.fre, JP.ger  # 기존 이름(일본판)


def detect_profile(elf):
    """코드 세그먼트 끝으로 지역판 식별. 패치 적용 시 원래 명령 값으로 한 번 더 검증된다."""
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    _, _, _, va, _, fs, _, _ = struct.unpack_from(">IIQQQQQQ", elf, phoff)
    hits = [p for p in PROFILES.values() if va + fs in (p.text_end, text_end_new(p))]  # 원본 / 패치 후
    if len(hits) != 1:
        raise ValueError(f"알 수 없는 EBOOT (코드 끝 {va + fs:#x}) — 지원: {', '.join(PROFILES)}")
    return hits[0]


def _hi_lo(addr):
    lo = addr & 0xFFFF
    lo = lo - 0x10000 if lo & 0x8000 else lo
    return (addr - lo) >> 16, lo


def _load(rd, addr):
    hi, lo = _hi_lo(addr)
    return [asm.lis(rd, hi), asm.addic(rd, rd, lo)]


def _suffix_function(p):
    """자막 언어 접미사 함수(일본판 0x28cc0c): 1→fre, 2→ger, 그 외→NULL 을 그 외→eng 로."""
    base = p.suffix_fn
    lang_hi, lang_lo = _hi_lo(p.lang)
    # 원래: cmpwi 3개 + 분기 4개로 1→fre, 2→ger, 그 외→li r3,0
    old = (asm.lis(3, lang_hi), asm.lwz(3, lang_lo, 3), 0x2C030001, 0x2C830002, 0x2F030000, 0x4181000C,
           0x40990024, 0x48000014, 0x4185001C, *_load(3, p.ger), 0x48000014,
           *_load(3, p.fre), 0x48000008, 0x38600000, 0x4E800020)
    fre_at, ger_at = base + 4 * 9, base + 4 * 12
    new = [asm.lis(3, lang_hi), asm.lwz(3, lang_lo, 3),
           asm.cmpwi(3, 1), asm.beq(base + 12, fre_at),
           asm.cmpwi(3, 2), asm.beq(base + 20, ger_at),
           *_load(3, p.eng), asm.BLR, *_load(3, p.fre), asm.BLR, *_load(3, p.ger), asm.BLR]
    return _rewrite(base, old, new, "자막 접미사 함수: 영어/기타 → eng")


def _playmovie_branch(p):
    """PlayMovie 메시지 함수의 자막 접미사 분기(일본판 0xfc88c8~): 영어/기타 r30=r29(0) → "eng".
    직전 `cmpwi r3,1` 의 cr0 를 그대로 쓴다."""
    base = p.playmovie_cmp + 8
    join = base + 4 * 13
    old = (0x41810010, 0x2C030000, 0x40810028, 0x48000018, 0x2C030002, 0x4181001C, *_load(30, p.ger),
           0x48000014, *_load(30, p.fre), 0x48000008, 0x63BE0000)
    ger_at, fre_at = base + 4 * 6, base + 4 * 9

    def load(at, addr):
        return [*_load(30, addr), asm.b(at + 8, join)]

    new = [asm.beq(base, fre_at),
           asm.cmpwi(3, 2), asm.beq(base + 8, ger_at),
           *load(base + 12, p.eng), *load(ger_at, p.ger), *load(fre_at, p.fre)]
    return _rewrite(base, old, new, "PlayMovie 자막 접미사: 영어/기타 → eng")


def subtitle_patches(p):
    eng_hi, eng_lo = _hi_lo(p.eng)
    return (
        # 부트플로/어트랙트 영상 플레이어: 언어 0(영어)/기타는 r30=0 → 자막 생략.
        # `li r30,0` 을 nop 으로 바꿔 r30="eng" 유지 → *_eng.sub 를 읽게 한다.
        # r30="eng" 는 이 함수 앞부분(lis/addic r30)이 넣는다 — 그 두 명령도 확인한다.
        Patch(p.bootflow_li - 0x40, asm.lis(30, eng_hi), asm.lis(30, eng_hi), "확인: 부트플로 r30 = eng (상위)"),
        Patch(p.bootflow_li - 0x3C, asm.addic(30, 30, eng_lo), asm.addic(30, 30, eng_lo), "확인: 부트플로 r30 = eng (하위)"),
        Patch(p.bootflow_li, 0x3BC00000, 0x60000000, "영어 경로 FMV 자막 활성화 (li r30,0 → nop)"),
        *_suffix_function(p),
        # 위 재작성은 직전 `cmpwi r3,1` 의 cr0 를 그대로 쓰므로 그 명령이 그대로인지 확인만 한다
        Patch(p.playmovie_cmp, 0x2C030001, 0x2C030001, "확인: PlayMovie 분기 앞 cmpwi r3,1"),
        *_playmovie_branch(p),
    )


SUBTITLE_PATCHES = subtitle_patches(JP)


def _data(vaddr, old, new, why):
    """vaddr 부터 old 바이트열(4의 배수, 슬롯 전체)을 new 로 바꾸는 단어 패치들. new 는 0 으로 채운다."""
    if vaddr & 3 or len(old) & 3 or len(new) > len(old):
        raise ValueError("데이터 패치 정렬/길이 오류")
    new = new.ljust(len(old), b"\0")
    return tuple(Patch(vaddr + i, int.from_bytes(old[i:i + 4], "big"), int.from_bytes(new[i:i + 4], "big"), why)
                 for i in range(0, len(old), 4))


# 0x3812ec 날짜 문자열 함수: 언어별 snprintf(buf, 0x20, 형식, ...). 영어(0x16) 분기는
# ("%s %02d, %04d", 월이름, 일=r30, 연도=r29) / 연도 없음 ("%s %02d", 월이름, 일).
# 한국어 어순("2011년 2월 2일")을 위해 영어 분기 인자를 (연도, 월이름, 일)로 바꾸고,
# 이 게임이 쓰지 않는 스페인어(0x17) 형식 칸 2개에 한국어 형식을 넣어 가리키게 한다.
KO_DATE_YMD, KO_DATE_MD = JP.ko_date_ymd, JP.ko_date_md  # 기존 이름(일본판)


def date_patches(p):
    def lo_same_hi(old_addr, new_addr):
        # 영어 분기는 `lis r5,hi` 를 그대로 두고 addic 하위만 바꾸므로 상위가 같아야 한다
        if _hi_lo(old_addr)[0] != _hi_lo(new_addr)[0]:
            raise ValueError(f"{new_addr:#x}: 형식 문자열 상위 주소가 달라 addic 만으로 못 바꿈")
        return _hi_lo(old_addr)[1], _hi_lo(new_addr)[1]

    ymd_old, ymd_new = lo_same_hi(p.date_en_fmt, p.ko_date_ymd)
    md_old, md_new = lo_same_hi(p.date_en_fmt_noyear, p.ko_date_md)
    d, n = p.date_en, p.date_num
    return (
    *_data(p.ko_date_ymd, b"%02d de %s de %04d".ljust(24, b"\0"), "%d년 %s %d일".encode(), "날짜 형식: 연 월 일"),
    *_data(p.ko_date_md, b"%02d de %s".ljust(16, b"\0"), "%s %d일".encode(), "날짜 형식: 월 일"),
    Patch(d, asm.lwz(6, 0x74, 1), asm.lwz(7, 0x74, 1), "날짜 영어 분기: 월이름 → 2번째 인자"),
    Patch(d + 0x4, asm.mr(8, 29), asm.mr(6, 29), "날짜 영어 분기: 연도 → 1번째 인자"),
    Patch(d + 0x8, asm.addic(5, 5, ymd_old), asm.addic(5, 5, ymd_new), "날짜 영어 분기: 형식 → 연 월 일"),
    Patch(d + 0x14, asm.mr(7, 30), asm.mr(8, 30), "날짜 영어 분기: 일 → 3번째 인자"),
    Patch(d + 0x30, asm.addic(5, 5, md_old), asm.addic(5, 5, md_new), "날짜 영어 분기(연도 없음): 형식 → 월 일"),
    # 같은 함수의 숫자형 영어(0xa) 분기 0x381460: ("%02d/%02d/%04d", 월=r3, 일=r30, 연=r29) →
    # 기존 형식 표의 "%04d.%02d.%02d"(0x12d2e40 = r6 0x12d2dc8 + 0x78)에 (연, 월, 일). r3 는 버퍼 주소로
    # 덮이기 전에 읽어야 하므로 순서를 바꾼다. 연도 없음은 "%02d/%02d"(r4) → "%02d.%02d"(r4 + 0x78).
    Patch(n, asm.mr(5, 6), asm.addic(5, 6, 0x78), "숫자 날짜: 형식 → %04d.%02d.%02d"),
    Patch(n + 0x4, asm.mr(6, 3), asm.mr(7, 3), "숫자 날짜: 월 → 2번째 인자"),
    Patch(n + 0x10, asm.mr(7, 30), asm.mr(6, 29), "숫자 날짜: 연 → 1번째 인자"),
    Patch(n + 0x14, asm.mr(8, 29), asm.mr(8, 30), "숫자 날짜: 일 → 3번째 인자"),
    Patch(n + 0x20, asm.mr(5, 4), asm.addic(5, 4, 0x78), "숫자 날짜(연도 없음): 형식 → %02d.%02d"),
    )


DATE_PATCHES = date_patches(JP)

# EBOOT 에 텍스트로 내장된 EA MemoryFramework 설정(finalmemoryconfig.h, ELF 0x12a6d72~).
# "AddAllocator[.ps3]  <이름>  <형식>  [ size=<N>M, ..." 의 크기를 같은 자릿수로만 바꾼다(문자열 길이 유지).
# 조정 근거·검증은 docs/freeze_investigation.md.
MEMCFG_AT = JP.memcfg_at  # 기존 이름(일본판)
POOL_SIZES = {}  # 이름: MB — 빈 dict 이면 패치 없음 (FONT_GEN·FRONTEND_GEN 확대 모두 멈춤을 못 고침)


def _memcfg(elf, p=None):
    p = p or detect_profile(elf)
    off = _offset(elf, p.memcfg_at)
    end = elf.index(b"\0", off)
    return off, elf[off:end]


def memory_patches(elf, sizes=None, p=None):
    p = p or detect_profile(elf)
    sizes = POOL_SIZES if sizes is None else sizes
    off, cfg = _memcfg(elf, p)
    out = []
    for name, mb in sizes.items():
        hits = [m for m in re.finditer(rb"AddAllocator(\.ps3)?[ 	]+" + re.escape(name.encode())
                                       + rb"[ 	]+\w+[ 	]+\[ size=(\d+)M", cfg)]
        if len(hits) != 1:
            raise ValueError(f"메모리 설정에서 {name} 을(를) 하나로 찾지 못함: {len(hits)}")
        m = hits[0]
        old_txt, new_txt = m.group(2), str(mb).encode()
        if len(old_txt) != len(new_txt):
            raise ValueError(f"{name}: 자릿수가 달라 바꿀 수 없음 {old_txt} → {new_txt}")
        for i, (a, b) in enumerate(zip(old_txt, new_txt)):
            if a == b:
                continue
            va = p.memcfg_at + m.start(2) + i
            word_at = va & ~3
            shift = 8 * (3 - (va - word_at))
            woff = _offset(elf, word_at)
            old = struct.unpack_from(">I", elf, woff)[0]
            out.append(Patch(word_at, old, (old & ~(0xFF << shift)) | (b << shift),
                             f"메모리 설정: {name} {old_txt.decode()}M → {mb}M"))
    # 같은 단어를 두 번 고치는 경우는 합친다
    merged = {}
    for pt in out:
        if pt.vaddr in merged:
            prev = merged[pt.vaddr]
            mask = prev.old ^ pt.new
            merged[pt.vaddr] = Patch(pt.vaddr, prev.old, (prev.new & ~(prev.old ^ pt.new)) | (pt.new & (prev.old ^ pt.new)), prev.why + " / " + pt.why)
        else:
            merged[pt.vaddr] = pt
    return tuple(merged.values())


# 시합 중 멈춤 수정(docs/freeze_investigation.md): 리플레이 기록기는 작업 구조체 하나를 열기·쓰기·닫기에 돌려쓴다.
# 비동기 작업 일꾼(0x7bc0c0)은 "완료(+8) 기록 → 완료 콜백 호출" 순서라, 완료를 본 기록기가 콜백보다 먼저
# 작업을 재사용하면(+0x18 = 0) 쓰기 완료 콜백 0x4a5010 이
#   lwz r3,0x18(r3) / li r4,0 / stb r4,0(r3) / blr
# 에서 0번지에 쓰고 정지한다(원본에도 있는 경쟁, 한글판에서 자주 남).
# 고침: 일꾼이 완료를 기록하기 "전에" 이 콜백의 바쁨 플래그를 지우고(정상 경로·취소 경로 둘 다),
# 콜백 자체는 아무것도 쓰지 않는다. 콜백은 +0x18 이 이미 0이면(경쟁이 났던 경우) 없는 syscall(MARK_SYSCALL)을
# 불러 RPCS3 syscall 통계에 횟수를 남긴다(실기에서는 ENOSYS 반환뿐).
# 동굴은 코드 세그먼트 끝(0x16a2ce8)과 다음 세그먼트(0x16b0000) 사이 빈 공간을 늘려 쓴다.
TEXT_END, CAVE = JP.text_end, JP.cave  # 기존 이름(일본판)
MARK_SYSCALL, SC = 1023, 0x44000002
LWSYNC, BNELR = 0x7C2004AC, 0x4C820020
REPLAY_CB_OPD = JP.replay_cb_opd  # 리플레이 쓰기 콜백의 함수 기술자
WORKER_DONE, CANCEL_DONE = JP.worker_done, JP.cancel_done  # stw rX,8(job) — 완료 기록


def _li(rd, imm):
    return asm._d(14, rd, 0, imm)


def _addi(rd, ra, imm):
    return asm._d(14, rd, ra, imm)


def _stb(rs, d, ra):
    return asm._d(38, rs, ra, d)


def _stw(rs, d, ra):
    return asm._d(36, rs, ra, d)


def _cmpw(ra, rb):
    return 0x7C000000 | (ra << 16) | (rb << 11)


def _bne(at, target):
    return (16 << 26) | (4 << 21) | (2 << 16) | ((target - at) & 0xFFFC)


def _bl(at, target):
    return asm.b(at, target) | 1


def _clear_then_done(at, job, cb, res, t, opd):
    """cb(=작업 +0x1c)가 리플레이 콜백(opd)이면 *(job+0x18) 바쁨 플래그를 먼저 지우고, 완료(res)를 기록."""
    w = [] if cb is not None else [asm.lwz(t[0], 0x1C, job)]
    cb = t[0] if cb is None else cb
    w += [asm.lis(t[1], (opd + 0x8000) >> 16), _addi(t[1], t[1], opd & 0xFFFF), _cmpw(cb, t[1])]
    k = len(w)  # bne 위치, 건너뛸 곳 = lwsync
    w += [_bne(at + 4 * k, at + 4 * (k + 6)), asm.lwz(t[0], 0x18, job), asm.cmpwi(t[0], 0),
          asm.beq(at + 4 * (k + 3), at + 4 * (k + 6)), _li(t[1], 0), _stb(t[1], 0, t[0])]
    return w + [LWSYNC, _stw(res, 8, job), asm.BLR]


def _caves(p=JP):
    cb_at = p.cave
    cb = [asm.lwz(5, 0x18, 3), asm.cmpwi(5, 0), BNELR, _li(11, MARK_SYSCALL), SC, asm.BLR]
    w_at = cb_at + 4 * len(cb)
    worker = _clear_then_done(w_at, job=p.worker_job, cb=4, res=p.worker_res, t=(6, 7), opd=p.replay_cb_opd)
    c_at = w_at + 4 * len(worker)
    cancel = _clear_then_done(c_at, job=30, cb=None, res=4, t=(6, 7), opd=p.replay_cb_opd)
    return [(cb_at, cb), (w_at, worker), (c_at, cancel)]


def race_patches(p=JP):
    (cb_at, _), (w_at, _), (c_at, _) = _caves(p)
    out = [Patch(p.replay_cb, 0x80630018, asm.b(p.replay_cb, cb_at), "리플레이 쓰기 콜백: 쓰지 않고 경쟁 횟수만 표시"),
           Patch(p.worker_done, _stw(p.worker_res, 8, p.worker_job), _bl(p.worker_done, w_at), "일꾼: 플래그 지운 뒤 완료 기록"),
           Patch(p.cancel_done, _stw(4, 8, 30), _bl(p.cancel_done, c_at), "일꾼(취소): 플래그 지운 뒤 완료 기록")]
    for at, words in _caves(p):
        out += [Patch(at + 4 * i, 0, w, f"동굴 {at + 4 * i:#x}") for i, w in enumerate(words)]
    return tuple(out)


def text_end_new(p):
    return p.cave + 4 * sum(len(w) for _, w in _caves(p)) + 8


RACE_PATCHES = race_patches(JP)
TEXT_END_NEW = text_end_new(JP)


def extend_text(elf, new_end=None, p=None):
    """코드 세그먼트(첫 PT_LOAD, R+X) 크기를 new_end 까지 늘린다. 늘리는 영역은 파일에서 0 이어야 한다."""
    p = p or detect_profile(elf)
    new_end = text_end_new(p) if new_end is None else new_end
    out = bytearray(elf)
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    t, fl, off, va, pa, fs, ms, al = struct.unpack_from(">IIQQQQQQ", elf, phoff)
    if t != 1 or not fl & 1 or va + fs != p.text_end or fs != ms:
        raise ValueError(f"예상한 코드 세그먼트가 아님: va={va:#x} filesz={fs:#x}")
    grow = new_end - (va + fs)
    if any(elf[off + fs:off + fs + grow]):
        raise ValueError("늘릴 영역이 비어 있지 않음")
    struct.pack_into(">QQ", out, phoff + 0x20, fs + grow, ms + grow)
    return bytes(out)


def patches_for(p):
    return subtitle_patches(p) + date_patches(p) + race_patches(p)


ALL_PATCHES = patches_for(JP)


def _offset(elf, vaddr):
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    for i in range(phnum):
        p_type, _, off, va, _, filesz, _, _ = struct.unpack_from(">IIQQQQQQ", elf, phoff + i * phentsize)
        if p_type == 1 and va <= vaddr and vaddr + 4 <= va + filesz:
            return off + vaddr - va
    raise KeyError(hex(vaddr))


def apply_all(elf, pool_sizes=None, profile=None):
    """자막·날짜·NULL 확인(동굴 포함)·메모리 설정 패치 전부. 지역판은 EBOOT 로 자동 식별."""
    p = profile or detect_profile(elf)
    elf = extend_text(elf, p=p)
    return apply(elf, patches_for(p) + memory_patches(elf, pool_sizes, p))


def apply(elf, patches):
    if elf[:6] != b"\x7fELF\x02\x02":
        raise ValueError("ELF64 BE 아님 (복호화 EBOOT 필요)")
    out = bytearray(elf)
    seen = set()
    for p in patches:
        off = _offset(elf, p.vaddr)
        if off in seen:
            raise ValueError(f"중복 패치 {p.vaddr:#x}")
        seen.add(off)
        cur, = struct.unpack_from(">I", elf, off)
        if cur != p.old:
            raise ValueError(f"{p.vaddr:#x}: 원래 값 {cur:#010x} != 기대 {p.old:#010x} ({p.why})")
        struct.pack_into(">I", out, off, p.new)
    return bytes(out)
