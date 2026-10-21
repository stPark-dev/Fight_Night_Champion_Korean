"""EA 'chunkzip' v2 컨테이너.

  0x00 'chunkzip' / 0x08 u32 ver=2 / 0x0C u32 원본 크기 / 0x10 u32 청크 크기
  0x14 u32 청크 수 / 0x18 u32 정렬(16) / 0x1C..0x27 0
  청크: u32 압축 길이, u32 타입(1=raw deflate), 페이로드(시작이 정렬 경계). 마지막 뒤 패딩 없음.
"""
import struct
import zlib

MAGIC = b"chunkzip"
HEAD = struct.Struct(">8sIIIII12x")
CHUNK = struct.Struct(">II")
TYPE_DEFLATE = 1


def _payload_pos(pos, align):
    return (pos + CHUNK.size + align - 1) // align * align - CHUNK.size


def declared_size(data):
    return HEAD.unpack_from(data, 0)[2]


def unpack(data):
    magic, ver, total, _csz, nch, align = HEAD.unpack_from(data, 0)
    if magic != MAGIC or ver != 2:
        raise ValueError("chunkzip v2 아님")
    pos, out = HEAD.size, bytearray()
    for i in range(nch):
        pos = _payload_pos(pos, align)
        clen, ctype = CHUNK.unpack_from(data, pos)
        pos += CHUNK.size
        if ctype != TYPE_DEFLATE:
            raise ValueError(f"청크 {i}: 미지원 타입 {ctype}")
        out += zlib.decompress(data[pos:pos + clen], -15)
        pos += clen
    if len(out) != total:
        raise ValueError(f"해제 크기 {len(out)} != 선언 {total}")
    return bytes(out)


def pack(raw, chunk_size=0x20000, align=16):
    chunks = [raw[i:i + chunk_size] for i in range(0, len(raw), chunk_size)]
    out = bytearray(HEAD.pack(MAGIC, 2, len(raw), chunk_size, len(chunks), align))
    for c in chunks:
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        comp = co.compress(c) + co.flush()
        pad = _payload_pos(len(out), align) - len(out)
        out += bytes(pad) + CHUNK.pack(len(comp), TYPE_DEFLATE) + comp
    return bytes(out)
