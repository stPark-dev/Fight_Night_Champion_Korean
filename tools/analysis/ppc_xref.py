"""PS3 PPU ELF(복호화본) 문자열 역참조 탐색 (분석 전용).

사용: python ppc_xref.py EBOOT.elf <문자열> [...]
문자열 vaddr → 그 값을 담은 TOC 슬롯 → `lwz/ld rX, off(r2)` 로 슬롯을 읽는 명령 위치.
"""
import struct
import sys
from functools import lru_cache

import capstone


class Elf:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        d = self.d
        assert d[:4] == b"\x7fELF" and d[4] == 2
        self.entry, phoff = struct.unpack_from(">QQ", d, 0x18)
        phentsize, phnum = struct.unpack_from(">HH", d, 0x36)
        self.segs = []
        for i in range(phnum):
            p_type, flags, off, vaddr, _, filesz, memsz, _ = struct.unpack_from(">IIQQQQQQ", d, phoff + i * phentsize)
            if p_type == 1:
                self.segs.append((vaddr, off, filesz, flags))
        # entry는 OPD를 가리킴: (func addr u32, toc u32)
        fa, self.toc = struct.unpack_from(">II", d, self.off(self.entry))

    def off(self, va):
        for v, o, sz, _ in self.segs:
            if v <= va < v + sz:
                return o + va - v
        raise KeyError(hex(va))

    def va(self, off):
        for v, o, sz, _ in self.segs:
            if o <= off < o + sz:
                return v + off - o
        raise KeyError(hex(off))

    def u32(self, va):
        return struct.unpack_from(">I", self.d, self.off(va))[0]

    def code_segs(self):
        return [(v, o, sz) for v, o, sz, f in self.segs if f & 1]

    def data_segs(self):
        return [(v, o, sz) for v, o, sz, f in self.segs if not f & 1]


def find_all(d, needle):
    i = d.find(needle)
    while i >= 0:
        yield i
        i = d.find(needle, i + 1)


def slots_holding(elf, value):
    pat = struct.pack(">I", value)
    out = []
    for v, o, sz in elf.data_segs():
        for i in find_all(elf.d[o:o + sz], pat):
            if i % 4 == 0:
                out.append(v + i)
    return out


def r2_loads(elf, slot):
    """`lwz/ld rD, disp(r2)` 중 r2+disp == slot 인 명령 주소들."""
    disp = slot - elf.toc
    if not -0x8000 <= disp < 0x8000:
        return []
    hits = []
    for v, o, sz in elf.code_segs():
        code = elf.d[o:o + sz]
        for op, mask in ((32, 0), (58, 0)):  # lwz, ld
            for i in range(0, len(code), 4):
                w = struct.unpack_from(">I", code, i)[0]
                if w >> 26 == op and (w >> 16) & 31 == 2 and struct.unpack(">h", struct.pack(">H", w & 0xFFFF))[0] == (disp & ~3 if op == 58 else disp):
                    hits.append(v + i)
    return hits


def disasm(elf, va, n=40):
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    o = elf.off(va)
    return [f"{i.address:08x}: {i.mnemonic} {i.op_str}" for i in md.disasm(elf.d[o:o + 4 * n], va)]


if __name__ == "__main__":
    elf = Elf(sys.argv[1])
    print("entry", hex(elf.entry), "toc", hex(elf.toc), "segs", [(hex(v), hex(o), hex(s), f) for v, o, s, f in elf.segs])
    for s in sys.argv[2:]:
        for off in find_all(elf.d, s.encode() + b"\0"):
            va = elf.va(off)
            slots = slots_holding(elf, va)
            print(f"{s!r} @va {va:#x}: slots {[hex(x) for x in slots]}")
            for sl in slots:
                print("   loads", [hex(x) for x in r2_loads(elf, sl)])


def _s16(x):
    return x - 0x10000 if x & 0x8000 else x


def addr_refs(elf, targets, window=12):
    """`lis rA,H` / `addis rA,r2,H` 이후 window 명령 안의 `addi/lwz/ori rB, L(rA)` 로 만들어진 주소 중 targets 에 맞는 것."""
    targets = set(targets)
    hits = []
    for v, o, sz in elf.code_segs():
        code = elf.d[o:o + sz]
        n = len(code) // 4
        words = struct.unpack(f">{n}I", code[:n * 4])
        for i, w in enumerate(words):
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            if op != 15:  # addis (lis = addis rD,0,H)
                continue
            if ra == 0:
                hi = _s16(imm) << 16
            elif ra == 2:
                hi = elf.toc + (_s16(imm) << 16)
            else:
                continue
            for j in range(i + 1, min(i + 1 + window, n)):
                w2 = words[j]
                op2, rd2, ra2, imm2 = w2 >> 26, (w2 >> 21) & 31, (w2 >> 16) & 31, w2 & 0xFFFF
                if ra2 == rd and op2 in (14, 32, 34, 40, 36, 38, 44, 48, 52, 58):
                    a = (hi + _s16(imm2)) & 0xFFFFFFFF
                    if a in targets:
                        hits.append((v + 4 * j, a))
                if op2 == 24 and (w2 >> 21) & 31 == rd and ra2 == rd:  # ori rA,rS,L (rS=bits21-25)
                    a = (hi | imm2) & 0xFFFFFFFF
                    if a in targets:
                        hits.append((v + 4 * j, a))
                if (w2 >> 21) & 31 == rd and op2 not in (36, 38, 44, 37, 39, 45):  # rd 덮어쓰기
                    break
    return hits


def const_refs(elf, targets):
    """직선 구간 레지스터 상수 추적(li/lis/oris/ori/addi/addis, r2=TOC)으로 targets 주소를 만드는 명령 위치."""
    targets = set(targets)
    hits = []
    for v, o, sz in elf.code_segs():
        n = sz // 4
        words = struct.unpack(f">{n}I", elf.d[o:o + n * 4])
        regs = {}
        for i, w in enumerate(words):
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            val = None
            if op in (12, 14):  # addic / addi / li (SNC는 주소 계산에 addic를 씀)
                base = 0 if ra == 0 else (elf.toc if ra == 2 else regs.get(ra))
                if base is not None:
                    val = (base + _s16(imm)) & 0xFFFFFFFF
            elif op == 15:  # addis / lis
                base = 0 if ra == 0 else (elf.toc if ra == 2 else regs.get(ra))
                if base is not None:
                    val = (base + (_s16(imm) << 16)) & 0xFFFFFFFF
            elif op in (24, 25):  # ori / oris : rA = rS | imm  (rS=bits21-25 → dest ra)
                src = regs.get(rd)
                if src is not None:
                    regs[ra] = (src | (imm << 16 if op == 25 else imm)) & 0xFFFFFFFF
                    if regs[ra] in targets:
                        hits.append((v + 4 * i, regs[ra]))
                else:
                    regs.pop(ra, None)
                continue
            elif op == 32 and ra == 2:  # lwz rD, d(r2): TOC 슬롯 값(앵커 주소) 로드
                try:
                    regs[rd] = elf.u32(elf.toc + _s16(imm))
                except KeyError:
                    regs.pop(rd, None)
                continue
            elif op in (32, 34, 40, 42, 58) and ra in regs:  # load 주소
                a = (regs[ra] + _s16(imm & ~3 if op == 58 else imm)) & 0xFFFFFFFF
                if a in targets:
                    hits.append((v + 4 * i, a))
                regs.pop(rd, None)
                continue
            elif op == 18 and w & 1:  # bl: 휘발성 레지스터(r0, r3-r12)만 무효화
                for r in (0, *range(3, 13)):
                    regs.pop(r, None)
                continue
            elif op == 18 or w == 0x4E800020:  # b / blr → 상태 초기화
                regs = {}
                continue
            else:
                _clobber(regs, w)
                continue
            if val is None:
                regs.pop(rd, None)
                continue
            regs[rd] = val
            if val in targets:
                hits.append((v + 4 * i, val))
    return hits


_RA_DEST_OP31 = {28, 60, 124, 284, 316, 412, 444, 476, 24, 536, 792, 824, 26, 922, 954, 986, 27, 539, 794, 58, 826, 827}
_NO_DEST = {10, 11, 16, 17, 18, 19, 36, 37, 38, 39, 44, 45, 52, 53, 54, 55, 62, 2, 3}


def _clobber(regs, w):
    """명령이 쓰는 목적지 레지스터를 무효화. `mr`(or rA,rS,rS)은 값 복사."""
    op, rd, ra = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    if op in _NO_DEST:
        return
    if op == 31:
        xo = (w >> 1) & 0x3FF
        if xo == 444 and ((w >> 11) & 31) == rd:  # mr ra, rd
            if rd in regs:
                regs[ra] = regs[rd]
            else:
                regs.pop(ra, None)
            return
        if xo in (151, 183, 215, 247, 407, 439, 663, 695, 727, 759, 918, 662, 150, 214, 149, 181):  # stores
            return
        regs.pop(ra if xo in _RA_DEST_OP31 else rd, None)
        return
    if op in (20, 21, 23, 26, 27, 28, 29, 30):
        regs.pop(ra, None)
        return
    regs.pop(rd, None)
