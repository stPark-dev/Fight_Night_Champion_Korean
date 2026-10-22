"""DXT5(BC3) 인코딩(단순 끝점 방식)과 DDS 픽셀 교체.

색: 블록의 밝기 최소/최대 픽셀을 끝점으로(RGB565), 4단계 보간 중 가장 가까운 값.
알파: 블록 최소/최대를 끝점으로 8단계 보간 중 가장 가까운 값.
UI 글자 텍스처(대개 단색 + 알파 무늬)에는 이 정도로 충분하다.
"""
import struct


def _565(c):
    r, g, b = c
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _unpack565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def _color_block(px):
    lum = [r * 3 + g * 6 + b for r, g, b, _ in px]
    hi, lo = px[lum.index(max(lum))][:3], px[lum.index(min(lum))][:3]
    c0, c1 = _565(hi), _565(lo)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return struct.pack("<HHI", c0, c1, 0)
    e0, e1 = _unpack565(c0), _unpack565(c1)
    pal = [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1)), tuple((a + 2 * b) // 3 for a, b in zip(e0, e1))]
    idx = 0
    for i, (r, g, b, _) in enumerate(px):
        k = min(range(4), key=lambda j: (pal[j][0] - r) ** 2 + (pal[j][1] - g) ** 2 + (pal[j][2] - b) ** 2)
        idx |= k << (2 * i)
    return struct.pack("<HHI", c0, c1, idx)


def _alpha_block(px):
    al = [p[3] for p in px]
    a0, a1 = max(al), min(al)
    if a0 == a1:
        return bytes([a0, a1, 0, 0, 0, 0, 0, 0])
    pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    bits = 0
    for i, a in enumerate(al):
        k = min(range(8), key=lambda j: abs(pal[j] - a))
        bits |= k << (3 * i)
    return bytes([a0, a1]) + bits.to_bytes(6, "little")


def encode_dxt5(img):
    """PIL RGBA 이미지(가로·세로 4의 배수) → DXT5 블록 바이트열 (numpy 일괄 처리)."""
    import numpy as np
    img = img.convert("RGBA")
    w, h = img.size
    if w % 4 or h % 4:
        raise ValueError("크기는 4의 배수여야 함")
    a = np.asarray(img, dtype=np.int32)
    # (블록 수, 16, 4) — 블록은 행 우선, 블록 안 픽셀도 행 우선
    blk = a.reshape(h // 4, 4, w // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    n = blk.shape[0]
    # 알파
    al = blk[..., 3]
    a0, a1 = al.max(1), al.min(1)
    steps = np.arange(8)
    pal = np.empty((n, 8), np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    for i in range(1, 7):
        pal[:, i + 1] = ((7 - i) * a0 + i * a1) // 7
    aidx = np.abs(al[:, :, None] - pal[:, None, :]).argmin(2)
    aidx[a0 == a1] = 0
    abits = (aidx.astype(np.uint64) << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    # 색
    rgb = blk[..., :3]
    lum = rgb[..., 0] * 3 + rgb[..., 1] * 6 + rgb[..., 2]
    hi = rgb[np.arange(n), lum.argmax(1)]
    lo = rgb[np.arange(n), lum.argmin(1)]

    def to565(c):
        return ((c[:, 0] * 31 + 127) // 255) << 11 | ((c[:, 1] * 63 + 127) // 255) << 5 | ((c[:, 2] * 31 + 127) // 255)

    c0, c1 = to565(hi), to565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)

    def un565(v):
        return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31], 1)

    e0, e1 = un565(c0), un565(c1)
    cpal = np.stack([e0, e1, (2 * e0 + e1) // 3, (e0 + 2 * e1) // 3], 1)  # (n, 4, 3)
    d = ((rgb[:, :, None, :] - cpal[:, None, :, :]) ** 2).sum(3)
    cidx = d.argmin(2)
    cidx[c0 == c1] = 0
    cbits = (cidx.astype(np.uint64) << (2 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((n, 16), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for i in range(6):
        out[:, 2 + i] = (abits >> np.uint64(8 * i)) & np.uint64(0xFF)
    out[:, 8], out[:, 9] = c0 & 0xFF, c0 >> 8
    out[:, 10], out[:, 11] = c1 & 0xFF, c1 >> 8
    for i in range(4):
        out[:, 12 + i] = (cbits >> np.uint64(8 * i)) & np.uint64(0xFF)
    return out.tobytes()


def replace_dds_dxt5(dds, img):
    """원본 DDS(DXT5, 밉맵 없음)의 헤더를 유지하고 픽셀만 img 로 바꾼다."""
    if dds[:4] != b"DDS " or dds[84:88] != b"DXT5":
        raise ValueError("DXT5 DDS 아님")
    h, w = struct.unpack_from("<II", dds, 12)
    mips = struct.unpack_from("<I", dds, 28)[0]
    if mips > 1:
        raise ValueError("밉맵 있는 DDS 는 미지원")
    if img.size != (w, h):
        raise ValueError(f"크기 불일치 {img.size} != {(w, h)}")
    data = encode_dxt5(img)
    if 128 + len(data) > len(dds):
        raise ValueError("DDS 데이터 길이 불일치")
    return dds[:128] + data + dds[128 + len(data):]  # 뒤에 붙은 바이트(원본 8바이트 꼬리)는 보존
