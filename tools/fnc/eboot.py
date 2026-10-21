"""복호화된 EBOOT(ELF64 BE)에 명령 단위 패치 적용. 모든 패치는 원래 값 확인 후 적용."""
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


def _offset(elf, vaddr):
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    for i in range(phnum):
        p_type, _, off, va, _, filesz, _, _ = struct.unpack_from(">IIQQQQQQ", elf, phoff + i * phentsize)
        if p_type == 1 and va <= vaddr and vaddr + 4 <= va + filesz:
            return off + vaddr - va
    raise KeyError(hex(vaddr))


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
