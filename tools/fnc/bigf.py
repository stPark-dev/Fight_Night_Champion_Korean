"""fe.big 안의 중첩 'BIGF' 아카이브(EA BIG 변형) 읽기/교체.

  0x00 'BIGF' / 0x04 LE u32 본문 크기(마지막 데이터 끝을 4바이트 정렬) / 0x08 BE u32 항목 수 / 0x0C BE u32 헤더 길이
  0x10 항목: BE u32 오프셋, BE u32 크기, 이름\\0  … 그 뒤 'L286' 꼬리표 등(헤더 길이까지), 데이터는 64바이트 정렬
  크기 0 항목(sg1, sg2 같은 구획 표시)은 다음 데이터 항목의 오프셋을 가리킨다.
  본문 뒤에 16바이트 꼬리가 붙는다(원본 그대로 보존).
"""
import struct
from dataclasses import dataclass, replace

ALIGN = 64


def _align(n):
    return (n + ALIGN - 1) // ALIGN * ALIGN


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes


@dataclass(frozen=True)
class Bigf:
    entries: tuple
    tail: bytes      # 항목 표 뒤 ~ 헤더 길이까지(‘L286’ 꼬리표)
    pad: bytes       # 헤더 길이 ~ 첫 데이터 사이 바이트(원본 그대로 보존)
    trailer: bytes   # 본문 뒤 꼬리

    @classmethod
    def parse(cls, raw):
        if raw[:4] != b"BIGF":
            raise ValueError("BIGF 아님")
        body = struct.unpack_from("<I", raw, 4)[0]
        if body > len(raw):
            raise ValueError("BIGF 크기 필드 불일치")
        n, hdr = struct.unpack_from(">II", raw, 8)
        p, items = 16, []
        for _ in range(n):
            off, size = struct.unpack_from(">II", raw, p)
            e = raw.index(b"\0", p + 8)
            items.append((raw[p + 8:e].decode("latin1"), off, size))
            p = e + 1
        first = min((off for _, off, size in items if size), default=_align(hdr))
        entries = tuple(Entry(name, bytes(raw[off:off + size])) for name, off, size in items)
        end = max((off + size for _, off, size in items), default=first)
        if (end + 3) & ~3 != body:
            raise ValueError(f"BIGF 본문 크기 {body} != 데이터 끝 {end}")
        return cls(entries, bytes(raw[p:hdr]), bytes(raw[hdr:first]), bytes(raw[body:]))

    def replaced(self, files):
        names = {e.name for e in self.entries}
        missing = set(files) - names
        if missing:
            raise KeyError(sorted(missing))
        return replace(self, entries=tuple(replace(e, data=files.get(e.name, e.data)) for e in self.entries))

    def build(self):
        table = b"".join(struct.pack(">II", 0, 0) + e.name.encode("latin1") + b"\0" for e in self.entries)
        hdr = 16 + len(table) + len(self.tail)
        pos = hdr + len(self.pad)
        offsets = []
        for e in self.entries:
            if e.data:
                pos = _align(pos)
            offsets.append(pos)
            pos += len(e.data)
        # 크기 0 항목은 다음 데이터 항목 오프셋을 가리킨다
        for i in range(len(self.entries) - 2, -1, -1):
            if not self.entries[i].data:
                offsets[i] = offsets[i + 1]
        body = (pos + 3) & ~3
        out = bytearray(body + len(self.trailer))
        out[:4] = b"BIGF"
        struct.pack_into(">II", out, 8, len(self.entries), hdr)
        p = 16
        for e, off in zip(self.entries, offsets):
            struct.pack_into(">II", out, p, off, len(e.data))
            p += 8 + len(e.name) + 1
            out[p - len(e.name) - 1:p - 1] = e.name.encode("latin1")
        out[p:hdr] = self.tail
        out[hdr:hdr + len(self.pad)] = self.pad
        for e, off in zip(self.entries, offsets):
            out[off:off + len(e.data)] = e.data
        out[body:] = self.trailer
        struct.pack_into("<I", out, 4, body)
        return bytes(out)
