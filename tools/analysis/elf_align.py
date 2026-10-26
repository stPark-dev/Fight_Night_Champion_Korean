"""두 PS3 ELF(같은 게임 다른 지역판)의 주소 대응 구간 계산 (분석 전용).

사용: python elf_align.py A.elf B.elf  → A 주소 구간별 (B - A) 차이
A의 64바이트 조각을 일정 간격으로 B에서 유일하게 찾고, 같은 차이가 이어지는 구간으로 묶는다.
"""
import sys

from ppc_xref import Elf


def anchors(a, b, step=0x400, size=64):
    out = []
    for v, o, sz, _ in a.segs:
        if not sz:
            continue
        for x in range(0, sz - size, step):
            sig = a.d[o + x:o + x + size]
            if len(set(sig)) < 8:  # 0 채움 등 흔한 패턴 제외
                continue
            i = b.d.find(sig)
            if i < 0 or b.d.find(sig, i + 1) >= 0:
                continue
            try:
                out.append((v + x, b.va(i) - (v + x)))
            except KeyError:
                pass
    return out


def runs(points):
    res = []
    for va, d in points:
        if res and res[-1][2] == d:
            res[-1][1] = va
        else:
            res.append([va, va, d])
    return res


if __name__ == "__main__":
    a, b = Elf(sys.argv[1]), Elf(sys.argv[2])
    pts = anchors(a, b)
    for s, e, d in runs(pts):
        print(f"{s:#010x}-{e:#010x}  delta {d:+#x}")
