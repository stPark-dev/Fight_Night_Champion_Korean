"""EA RefPack(QFS, 매직 10 FB) 압축 해제·압축.

압축은 리터럴 블록만 쓰는 단순 형식(유효한 RefPack 스트림이며 크기는 원본보다 약간 크다).
"""


def is_refpack(data):
    return len(data) > 5 and data[1] == 0xFB and data[0] & 0x3E == 0x10


def unpack(src):
    flags = src[0]
    if src[1] != 0xFB:
        raise ValueError("RefPack 아님")
    p = 2
    big = flags & 0x80
    if flags & 0x01:  # 압축 크기 필드
        p += 4 if big else 3
    size = int.from_bytes(src[p:p + (4 if big else 3)], "big")
    p += 4 if big else 3
    out = bytearray()
    while p < len(src):
        b0 = src[p]
        if b0 < 0x80:
            b1 = src[p + 1]
            p += 2
            lit = b0 & 3
            n, off = ((b0 >> 2) & 7) + 3, ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[p + 1], src[p + 2]
            p += 3
            lit = b1 >> 6
            n, off = (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[p + 1], src[p + 2], src[p + 3]
            p += 4
            lit = b0 & 3
            n, off = ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            lit = ((b0 & 0x1F) << 2) + 4
            out += src[p + 1:p + 1 + lit]
            p += 1 + lit
            continue
        else:
            lit = b0 & 3
            out += src[p + 1:p + 1 + lit]
            break
        out += src[p:p + lit]
        p += lit
        if off > len(out):
            raise ValueError("RefPack 참조가 출력 앞을 넘음")
        for _ in range(n):
            out.append(out[-off])
    if len(out) != size:
        raise ValueError(f"RefPack 크기 불일치 {len(out)} != {size}")
    return bytes(out)


def pack_literal(data):
    """리터럴 전용 RefPack: 112바이트 블록(0xFB) + 마지막 0~3바이트(0xFC~0xFF)."""
    n = len(data)
    if n >= 1 << 24:
        out = bytearray([0x90, 0xFB]) + n.to_bytes(4, "big")
    else:
        out = bytearray([0x10, 0xFB]) + n.to_bytes(3, "big")
    p = 0
    while n - p >= 4:
        lit = min(112, (n - p) & ~3)
        out.append(0xE0 + (lit - 4) // 4)
        out += data[p:p + lit]
        p += lit
    rest = n - p
    out.append(0xFC + rest)
    out += data[p:]
    return bytes(out)


def _emit_literals(out, data, start, end):
    """[start, end) 리터럴 중 4의 배수 부분을 0xE0~0xFB 블록으로 내보내고 남은 0~3바이트 길이를 돌려준다."""
    p = start
    while end - p >= 4:
        lit = min(112, (end - p) & ~3)
        out.append(0xE0 + (lit - 4) // 4)
        out += data[p:p + lit]
        p += lit
    return end - p


def _encodable(length, off):
    """참조 형식(2/3/4바이트)으로 표현 가능한 (길이, 거리) 인지."""
    return ((3 <= length <= 10 and off <= 1024) or (4 <= length <= 67 and off <= 16384)
            or (5 <= length and off <= 131072))


def pack(data, max_chain=16):
    """그리디 LZ RefPack 압축(해시 체인). 원본 EA 압축만큼은 아니지만 리터럴 전용보다 훨씬 작다."""
    n = len(data)
    out = bytearray([0x10, 0xFB] if n < 1 << 24 else [0x90, 0xFB])
    out += n.to_bytes(3 if n < 1 << 24 else 4, "big")
    head, prev = {}, [0] * n
    lit_start = p = 0
    while p < n:
        best_len = best_off = 0
        if p + 3 <= n:
            key = data[p:p + 3]
            cand = head.get(key, -1)
            chain = 0
            while cand >= 0 and chain < max_chain:
                off = p - cand
                if off > 131072:
                    break
                ln = 3
                limit = min(1028, n - p)
                while ln < limit and data[cand + ln] == data[p + ln]:
                    ln += 1
                if ln > best_len and _encodable(ln, off):
                    best_len, best_off = ln, off
                    if ln == limit:
                        break
                cand = prev[cand] if prev[cand] != cand else -1
                chain += 1
        if best_len:
            rest = _emit_literals(out, data, lit_start, p)
            lit = data[p - rest:p]
            L, off = best_len, best_off - 1
            if L <= 10 and best_off <= 1024:
                out += bytes([((off >> 3) & 0x60) | ((L - 3) << 2) | rest, off & 0xFF])
            elif L <= 67 and best_off <= 16384:
                out += bytes([0x80 | (L - 4), (rest << 6) | (off >> 8), off & 0xFF])
            else:
                L = min(L, 1028)
                out += bytes([0xC0 | ((off >> 12) & 0x10) | (((L - 5) >> 6) & 0x0C) | rest,
                              (off >> 8) & 0xFF, off & 0xFF, (L - 5) & 0xFF])
            out += lit
            for q in range(p, min(p + L, n - 2)):
                k = data[q:q + 3]
                prev[q] = head.get(k, q)
                head[k] = q
            p += L
            lit_start = p
        else:
            if p + 3 <= n:
                k = data[p:p + 3]
                prev[p] = head.get(k, p)
                head[k] = p
            p += 1
    rest = _emit_literals(out, data, lit_start, n)
    out.append(0xFC + rest)
    out += data[n - rest:]
    return bytes(out)
