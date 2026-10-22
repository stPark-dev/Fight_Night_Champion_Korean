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
