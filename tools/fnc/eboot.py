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


ENG, FRE, GER = 0x12C59AC, 0x12C8BB0, 0x12C59BC  # 접미사 문자열 주소


def _hi_lo(addr):
    lo = addr & 0xFFFF
    lo = lo - 0x10000 if lo & 0x8000 else lo
    return (addr - lo) >> 16, lo


def _suffix_function():
    """0x28cc0c 자막 언어 접미사 함수: 1→fre, 2→ger, 그 외→NULL 을 그 외→eng 로."""
    base = 0x28CC0C
    old = (0x3C600172, 0x80635CCC, 0x2C030001, 0x2C830002, 0x2F030000, 0x4181000C,
           0x40990024, 0x48000014, 0x4185001C, 0x3C60012C, 0x306359BC, 0x48000014,
           0x3C60012D, 0x30638BB0, 0x48000008, 0x38600000, 0x4E800020)

    def load(addr):
        hi, lo = _hi_lo(addr)
        return [asm.lis(3, hi), asm.addic(3, 3, lo), asm.BLR]

    fre_at, ger_at = base + 4 * 9, base + 4 * 12
    new = [asm.lis(3, 0x172), asm.lwz(3, 0x5CCC, 3),
           asm.cmpwi(3, 1), asm.beq(base + 12, fre_at),
           asm.cmpwi(3, 2), asm.beq(base + 20, ger_at),
           *load(ENG), *load(FRE), *load(GER)]
    return _rewrite(base, old, new, "자막 접미사 함수: 영어/기타 → eng")


def _playmovie_branch():
    """0xfc8678 PlayMovie 메시지 함수의 자막 접미사 분기(0xfc88c8~): 영어/기타 r30=r29(0) → "eng".
    직전 0xfc88c0 `cmpwi r3,1` 의 cr0 를 그대로 쓴다."""
    base, join = 0xFC88C8, 0xFC88FC
    old = (0x41810010, 0x2C030000, 0x40810028, 0x48000018, 0x2C030002, 0x4181001C, 0x3FC0012C,
           0x33DE59BC, 0x48000014, 0x3FC0012D, 0x33DE8BB0, 0x48000008, 0x63BE0000)
    ger_at, fre_at = base + 4 * 6, base + 4 * 9

    def load(at, addr):
        hi, lo = _hi_lo(addr)
        return [asm.lis(30, hi), asm.addic(30, 30, lo), asm.b(at + 8, join)]

    new = [asm.beq(base, fre_at),
           asm.cmpwi(3, 2), asm.beq(base + 8, ger_at),
           *load(base + 12, ENG), *load(ger_at, GER), *load(fre_at, FRE)]
    return _rewrite(base, old, new, "PlayMovie 자막 접미사: 영어/기타 → eng")


SUBTITLE_PATCHES = (
    # 부트플로/어트랙트 영상 플레이어: 언어 0(영어)/기타는 r30=0 → 자막 생략.
    # `li r30,0` 을 nop 으로 바꿔 r30="eng" 유지 → *_eng.sub 를 읽게 한다.
    Patch(0x28A2FC, 0x3BC00000, 0x60000000, "영어 경로 FMV 자막 활성화 (li r30,0 → nop)"),
    *_suffix_function(),
    # 위 재작성은 직전 `cmpwi r3,1`(0xfc88c0)의 cr0 를 그대로 쓰므로 그 명령이 그대로인지 확인만 한다
    Patch(0xFC88C0, 0x2C030001, 0x2C030001, "확인: PlayMovie 분기 앞 cmpwi r3,1"),
    *_playmovie_branch(),
)


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
KO_DATE_YMD, KO_DATE_MD = 0x12D2EF0, 0x12D2F08
DATE_PATCHES = (
    *_data(KO_DATE_YMD, b"%02d de %s de %04d".ljust(24, b"\0"), "%d년 %s %d일".encode(), "날짜 형식: 연 월 일"),
    *_data(KO_DATE_MD, b"%02d de %s".ljust(16, b"\0"), "%s %d일".encode(), "날짜 형식: 월 일"),
    Patch(0x381820, asm.lwz(6, 0x74, 1), asm.lwz(7, 0x74, 1), "날짜 영어 분기: 월이름 → 2번째 인자"),
    Patch(0x381824, asm.mr(8, 29), asm.mr(6, 29), "날짜 영어 분기: 연도 → 1번째 인자"),
    Patch(0x381828, asm.addic(5, 5, 0x2ED8), asm.addic(5, 5, KO_DATE_YMD & 0xFFFF), "날짜 영어 분기: 형식 → 연 월 일"),
    Patch(0x381834, asm.mr(7, 30), asm.mr(8, 30), "날짜 영어 분기: 일 → 3번째 인자"),
    Patch(0x381850, asm.addic(5, 5, 0x2EE8), asm.addic(5, 5, KO_DATE_MD & 0xFFFF), "날짜 영어 분기(연도 없음): 형식 → 월 일"),
    # 같은 함수의 숫자형 영어(0xa) 분기 0x381460: ("%02d/%02d/%04d", 월=r3, 일=r30, 연=r29) →
    # 기존 형식 표의 "%04d.%02d.%02d"(0x12d2e40 = r6 0x12d2dc8 + 0x78)에 (연, 월, 일). r3 는 버퍼 주소로
    # 덮이기 전에 읽어야 하므로 순서를 바꾼다. 연도 없음은 "%02d/%02d"(r4) → "%02d.%02d"(r4 + 0x78).
    Patch(0x381468, asm.mr(5, 6), asm.addic(5, 6, 0x78), "숫자 날짜: 형식 → %04d.%02d.%02d"),
    Patch(0x38146C, asm.mr(6, 3), asm.mr(7, 3), "숫자 날짜: 월 → 2번째 인자"),
    Patch(0x381478, asm.mr(7, 30), asm.mr(6, 29), "숫자 날짜: 연 → 1번째 인자"),
    Patch(0x38147C, asm.mr(8, 29), asm.mr(8, 30), "숫자 날짜: 일 → 3번째 인자"),
    Patch(0x381488, asm.mr(5, 4), asm.addic(5, 4, 0x78), "숫자 날짜(연도 없음): 형식 → %02d.%02d"),
)

# EBOOT 에 텍스트로 내장된 EA MemoryFramework 설정(finalmemoryconfig.h, ELF 0x12a6d72~).
# "AddAllocator[.ps3]  <이름>  <형식>  [ size=<N>M, ..." 의 크기를 같은 자릿수로만 바꾼다(문자열 길이 유지).
# 조정 근거·검증은 docs/freeze_investigation.md.
MEMCFG_AT = 0x12B6D72
POOL_SIZES = {}  # 이름: MB — 빈 dict 이면 패치 없음 (FONT_GEN·FRONTEND_GEN 확대 모두 멈춤을 못 고침)


def _memcfg(elf):
    off = _offset(elf, MEMCFG_AT)
    end = elf.index(b"\0", off)
    return off, elf[off:end]


def memory_patches(elf, sizes=None):
    sizes = POOL_SIZES if sizes is None else sizes
    off, cfg = _memcfg(elf)
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
            va = MEMCFG_AT + m.start(2) + i
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


# 시합 중 멈춤 임시책(docs/freeze_investigation.md): 리플레이 비동기 쓰기 완료 콜백 0x4a5010 은
#   lwz r3,0x18(r3) / li r4,0 / stb r4,0(r3) / blr   — 작업 구조체 +0x18(바쁨 플래그 주소)이 0이면 0번지에 써서 정지.
# 코드 세그먼트 끝(0x16a2ce8)과 다음 세그먼트(0x16b0000) 사이 빈 공간을 16바이트 늘려 동굴로 쓰고,
# 콜백을 "주소가 0이면 그냥 돌아감, 아니면 동굴에서 0을 쓰고 돌아감"으로 바꾼다.
TEXT_END, CAVE = 0x16A2CE8, 0x16A2CF0
TEXT_END_NEW = CAVE + 16


def _beqlr():
    return 0x4D820020  # bclr 12,2 (cr0 EQ 이면 복귀)


def _li(rd, imm):
    return asm._d(14, rd, 0, imm)


def _stb(rs, d, ra):
    return asm._d(38, rs, ra, d)


NULLCHECK_PATCHES = (
    Patch(0x4A5010, 0x80630018, 0x80630018, "확인: lwz r3,0x18(r3)"),
    Patch(0x4A5014, 0x38800000, asm.cmpwi(3, 0), "리플레이 쓰기 콜백: 플래그 주소 NULL 확인"),
    Patch(0x4A5018, 0x98830000, _beqlr(), "리플레이 쓰기 콜백: NULL 이면 복귀"),
    Patch(0x4A501C, asm.BLR, asm.b(0x4A501C, CAVE), "리플레이 쓰기 콜백: 동굴로"),
    Patch(CAVE, 0, _li(4, 0), "동굴: li r4,0"),
    Patch(CAVE + 4, 0, _stb(4, 0, 3), "동굴: stb r4,0(r3)"),
    Patch(CAVE + 8, 0, asm.BLR, "동굴: blr"),
)


def extend_text(elf, new_end=TEXT_END_NEW):
    """코드 세그먼트(첫 PT_LOAD, R+X) 크기를 new_end 까지 늘린다. 늘리는 영역은 파일에서 0 이어야 한다."""
    out = bytearray(elf)
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    t, fl, off, va, pa, fs, ms, al = struct.unpack_from(">IIQQQQQQ", elf, phoff)
    if t != 1 or not fl & 1 or va + fs != TEXT_END or fs != ms:
        raise ValueError(f"예상한 코드 세그먼트가 아님: va={va:#x} filesz={fs:#x}")
    grow = new_end - (va + fs)
    if any(elf[off + fs:off + fs + grow]):
        raise ValueError("늘릴 영역이 비어 있지 않음")
    struct.pack_into(">QQ", out, phoff + 0x20, fs + grow, ms + grow)
    return bytes(out)


ALL_PATCHES = SUBTITLE_PATCHES + DATE_PATCHES + NULLCHECK_PATCHES


def _offset(elf, vaddr):
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    for i in range(phnum):
        p_type, _, off, va, _, filesz, _, _ = struct.unpack_from(">IIQQQQQQ", elf, phoff + i * phentsize)
        if p_type == 1 and va <= vaddr and vaddr + 4 <= va + filesz:
            return off + vaddr - va
    raise KeyError(hex(vaddr))


def apply_all(elf, pool_sizes=None):
    """자막·날짜·NULL 확인(동굴 포함)·메모리 설정 패치 전부."""
    elf = extend_text(elf)
    return apply(elf, ALL_PATCHES + memory_patches(elf, pool_sizes))


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
