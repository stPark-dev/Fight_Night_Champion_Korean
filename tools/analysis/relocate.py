"""일본판 ELF의 주소를 다른 지역판 ELF에서 다시 찾기 (분석 전용).

- 데이터(문자열 등): 주변 바이트 창을 줄여 가며 유일 일치 검색
- 코드: 즉시값(16비트 변위·주소 조각·분기 오프셋)을 가린 명령 패턴(op+레지스터)으로 유일 일치 검색
"""
import struct


def find_unique(hay, needle):
    i = hay.find(needle)
    return i if i >= 0 and hay.find(needle, i + 1) < 0 else None


def relocate_data(a, b, va, windows=(48, 32, 24, 16, 12)):
    o = a.off(va)
    for w in windows:
        for before in (w, w // 2, 0):
            i = find_unique(b.d, a.d[o - before:o + w])
            if i is not None:
                return b.va(i + before)
    return None


def _mask(w):
    op = w >> 26
    if op in (16, 18):                     # bc, b: 오프셋 가림
        return w & (0xFFFF0003 if op == 16 else 0xFC000003)
    if op in (7, 8, 10, 11, 12, 13, 14, 15, 24, 25, 26, 27, 28, 29) or 32 <= op <= 58:
        return w & 0xFFFF0000                # D-형식: 즉시값 가림
    return w


def _masked_words(e, v, o, sz):
    n = sz // 4
    return [_mask(x) for x in struct.unpack(f">{n}I", e.d[o:o + n * 4])]


_cache = {}


def relocate_code(a, b, va, before=24, after=24):
    """va 주변 (before+after) 명령을 가린 패턴으로 b 코드 세그먼트에서 유일 일치."""
    key = id(b)
    if key not in _cache:
        v, o, sz, _ = b.segs[0]
        _cache[key] = (v, _masked_words(b, v, o, sz))
    bv, bwords = _cache[key]
    ao = a.off(va)
    pat = [_mask(x) for x in struct.unpack(f">{before + after}I", a.d[ao - 4 * before:ao + 4 * after])]
    hits = []
    first = pat[0]
    for i in range(len(bwords) - len(pat)):
        if bwords[i] == first and bwords[i:i + len(pat)] == pat:
            hits.append(i)
            if len(hits) > 1:
                return None
    return bv + 4 * (hits[0] + before) if hits else None
