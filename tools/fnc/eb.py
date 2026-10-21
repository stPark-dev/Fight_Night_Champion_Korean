"""EA 'EB' v3 빅파일 아카이브 (Fight Night Champion PS3).

레이아웃 (BE):
  0x00 'EB' u16 ver=3 / 0x04 u32 count / 0x08 u16 flags, u8 shift, u8 0
  0x0C u32 names_off / 0x10 u32 names_size / 0x14 u8 name_len, u8 dir_len, u16 ndirs
  0x1C u32 total_size / 0x30 entry[count] = (u32 offset>>shift, u32 0, u32 size, u32 hash)
  그 뒤 엔트리별 1 B 플래그(16 B 정렬), names_off에 이름 레코드(u16 dir + 이름),
  16 B 정렬된 디렉터리 테이블.
"""
import struct
from dataclasses import dataclass, replace

HEADER = struct.Struct(">2sHIHBBIIBBHII")
ENTRY = struct.Struct(">IIII")
ENTRIES_OFF = 0x30


def _align(n, a):
    return (n + a - 1) // a * a


def _check_layout(entries, tables_end, total):
    """제자리 교체(build)가 안전하려면: 데이터가 테이블 뒤, 파일 안, 서로 겹치지 않아야 한다."""
    spans = sorted((e.offset, e.offset + e.size, e.index) for e in entries)
    prev_end = tables_end
    for start, end, i in spans:
        if start < prev_end or end > total:
            raise ValueError(f"엔트리 {i}: 데이터 범위 {start:#x}-{end:#x} 가 겹치거나 범위 밖")
        prev_end = end


@dataclass(frozen=True)
class Entry:
    index: int
    path: str
    offset: int
    size: int
    hash: int


@dataclass(frozen=True)
class Archive:
    raw: bytes
    shift: int
    entries: tuple
    overrides: tuple = ()

    @classmethod
    def parse(cls, raw):
        (magic, ver, count, _flags, shift, _pad, names_off, _names_size,
         name_len, dir_len, ndirs, _unk, total) = HEADER.unpack_from(raw, 0)
        if magic != b"EB" or ver != 3:
            raise ValueError(f"EB v3 아님: {magic!r} v{ver}")
        if total != len(raw):
            raise ValueError(f"total_size {total} != 파일 크기 {len(raw)}")
        dir_base = _align(names_off + count * name_len, 16)
        dirs = [raw[dir_base + i * dir_len:dir_base + (i + 1) * dir_len].split(b"\0")[0].decode()
                for i in range(ndirs)]
        entries = []
        for i in range(count):
            off, zero, size, h = ENTRY.unpack_from(raw, ENTRIES_OFF + i * 16)
            if zero != 0:
                raise ValueError(f"엔트리 {i}: 미지원 필드 값 {zero:#x}")
            rec = names_off + i * name_len
            di, = struct.unpack_from(">H", raw, rec)
            if di >= ndirs:
                raise ValueError(f"엔트리 {i}: 디렉터리 인덱스 {di} >= {ndirs}")
            name = raw[rec + 2:rec + name_len].split(b"\0")[0].decode()
            entries.append(Entry(i, f"{dirs[di]}/{name}", off << shift, size, h))
        _check_layout(entries, dir_base + ndirs * dir_len, len(raw))
        return cls(bytes(raw), shift, tuple(entries))

    def _entry(self, path):
        for e in self.entries:
            if e.path == path:
                return e
        raise KeyError(path)

    def read(self, path):
        for p, data in self.overrides:
            if p == path:
                return data
        e = self._entry(path)
        return self.raw[e.offset:e.offset + e.size]

    def replaced(self, files):
        for path in files:
            self._entry(path)
        merged = dict(self.overrides)
        merged.update(files)
        return replace(self, overrides=tuple(merged.items()))

    def build(self):
        """변경 파일은 기존 슬롯에 맞으면 제자리, 아니면 끝에 추가. 나머지 바이트는 보존."""
        out = bytearray(self.raw)
        starts = sorted({e.offset for e in self.entries} | {len(self.raw)})
        unit = 1 << self.shift
        for path, data in self.overrides:
            e = self._entry(path)
            slot_end = next(s for s in starts if s > e.offset) if e.size else e.offset
            out[e.offset:e.offset + e.size] = bytes(e.size)
            if e.offset + len(data) <= slot_end:
                off = e.offset
            else:
                off = _align(len(out), unit)
                out.extend(bytes(off - len(out)))
                out.extend(bytes(len(data)))
            out[off:off + len(data)] = data
            ENTRY.pack_into(out, ENTRIES_OFF + e.index * 16, off >> self.shift, 0, len(data), e.hash)
        out.extend(bytes(_align(len(out), unit) - len(out)))
        struct.pack_into(">I", out, 0x1C, len(out))
        return bytes(out)
