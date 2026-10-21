"""EA T3DB v8 — LanguageStrings 테이블 1개짜리 로컬라이즈 DB.

  0x00 'DB\\0\\x08' 01000000 u32 파일크기 u32 0 u32 테이블수=1 / 0x14 CRC(0x00..0x14)
  0x18 'GJCv' u32 0 / 0x20 CRC(0x18..0x20)
  0x24 테이블 헤더: 0x28 u32 레코드 크기(16), 0x30 u32 문자열 영역 길이(트리 포함),
       0x34 u16 용량, u16 레코드 수 / 0x44 CRC(0x24..0x44)
  0x48 필드 3개 × 16 B / 0x78 레코드: u32 stringid 오프셋, u32 sourcetext 오프셋, i32 hashid, u32
  문자열 영역: 허프만 트리(노드 = BE u16×2, XX00 내부노드, 00XX 리프 바이트, 루트 0) 뒤
       stringid = u8 바이트수 + 비트열, sourcetext = BE u16 바이트수 + 비트열 (MSB 우선, 바이트 정렬)
       오프셋은 트리 시작 기준, 0xFFFFFFFF = null
  끝: 8 B 정렬 패딩 후 CRC(0x48..끝)
  CRC는 모두 CRC-32/MPEG-2.
"""
import heapq
import struct
from collections import Counter
from dataclasses import dataclass, replace

RECORDS_OFF = 0x78
REC = struct.Struct(">IIiI")
NULL = 0xFFFFFFFF
CRC_SPANS = ((0x14, 0x00), (0x20, 0x18), (0x44, 0x24))


def _make_table():
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
        table.append(c & 0xFFFFFFFF)
    return table


_CRC_TABLE = _make_table()


def crc32_mpeg2(data):
    crc = 0xFFFFFFFF
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[(crc >> 24) ^ b]
    return crc


def _crc_targets(raw):
    yield from ((at, start, at) for at, start in CRC_SPANS)
    yield (len(raw) - 4, 0x48, len(raw) - 4)


def verify_crcs(raw):
    """불일치하는 CRC 위치 목록 (정상이면 빈 목록)."""
    return [hex(at) for at, s, e in _crc_targets(raw)
            if struct.unpack_from(">I", raw, at)[0] != crc32_mpeg2(raw[s:e])]


@dataclass(frozen=True)
class Row:
    stringid: str
    text: object  # str | None
    hashid: int
    extra: int


# --- 허프만 -------------------------------------------------------------

def _codes(tree):
    codes, stack = {}, [(0, "")]
    while stack:
        node, prefix = stack.pop()
        for bit, child in enumerate(tree[node]):
            if child & 0xFF00:
                stack.append((child >> 8, prefix + str(bit)))
            else:
                codes[child] = prefix + str(bit)
    return codes


def build_tree(freq):
    """바이트 빈도로 허프만 트리 생성. 루트 0, 내부노드 최대 255개."""
    if len(freq) < 2:
        raise ValueError("허프만 심볼이 2개 미만")
    heap = [(n, i, ("leaf", sym)) for i, (sym, n) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    seq = len(heap)
    while len(heap) > 1:
        n1, _, a = heapq.heappop(heap)
        n2, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (n1 + n2, seq, ("node", a, b)))
        seq += 1
    nodes, queue = [], [heap[0][2]]
    while queue:  # BFS로 인덱스 부여 → 루트 0
        nodes.append(queue.pop(0))
        queue.extend(c for c in nodes[-1][1:] if c[0] == "node")
    index = {id(n): i for i, n in enumerate(nodes)}
    if len(nodes) > 255:
        raise ValueError("내부노드 255개 초과")
    return tuple(tuple((index[id(c)] << 8) if c[0] == "node" else c[1] for c in n[1:])
                 for n in nodes)


def _decode(raw, bitpos, nbytes, tree):
    out = bytearray()
    while len(out) < nbytes:
        node = 0
        while True:
            child = tree[node][(raw[bitpos >> 3] >> (7 - (bitpos & 7))) & 1]
            bitpos += 1
            if not child & 0xFF00:
                break
            node = child >> 8
        out.append(child)
    return bytes(out)


def _encode(data, codes):
    # 원본 인코더는 비트 수가 8의 배수여도 1바이트를 더 쓴다: floor(bits/8)+1
    bits = "".join(codes[b] for b in data)
    nbytes = len(bits) // 8 + 1
    return int(bits.ljust(nbytes * 8, "0"), 2).to_bytes(nbytes, "big")


# --- DB -----------------------------------------------------------------

@dataclass(frozen=True)
class LanguageDB:
    header: bytes  # 0x00..0x78 (길이/CRC는 build에서 다시 씀)
    tree: tuple
    rows: tuple

    @classmethod
    def parse(cls, raw):
        if raw[:4] != b"DB\x00\x08":
            raise ValueError("T3DB v8 아님")
        bad = verify_crcs(raw)
        if bad:
            raise ValueError(f"CRC 불일치: {bad}")
        rsz, = struct.unpack_from(">I", raw, 0x28)
        cap, nrec = struct.unpack_from(">HH", raw, 0x34)
        if rsz != REC.size or cap != nrec:
            raise ValueError(f"미지원 테이블 형태 rsz={rsz} cap={cap} n={nrec}")
        recs = [REC.unpack_from(raw, RECORDS_OFF + i * REC.size) for i in range(nrec)]
        base = RECORDS_OFF + nrec * REC.size
        tree_size = min(v for r in recs for v in r[:2] if v != NULL)
        tree = tuple(struct.unpack_from(">HH", raw, base + 4 * i) for i in range(tree_size // 4))

        def read(off, lfmt):
            if off == NULL:
                return None
            n, = struct.unpack_from(lfmt, raw, base + off)
            start = (base + off + struct.calcsize(lfmt)) * 8
            return _decode(raw, start, n, tree).decode("utf-8")

        rows = tuple(Row(read(a, ">B"), read(b, ">H"), h, x) for a, b, h, x in recs)
        return cls(bytes(raw[:RECORDS_OFF]), tree, rows)

    def by_id(self):
        return {r.stringid: r for r in self.rows}

    def with_texts(self, texts):
        ids = self.by_id()
        missing = [k for k in texts if k not in ids]
        if missing:
            raise KeyError(missing[:5])
        rows = tuple(replace(r, text=texts[r.stringid]) if r.stringid in texts else r
                     for r in self.rows)
        return replace(self, rows=rows)

    def _strings(self):
        for r in self.rows:
            yield r.stringid, ">B"
            yield r.text, ">H"

    def build(self, tree=None):
        if tree is None:
            freq = Counter()
            for s, _ in self._strings():
                if s is not None:
                    freq.update(s.encode("utf-8"))
            tree = build_tree(freq)
        codes = _codes(tree)
        area = bytearray(b"".join(struct.pack(">HH", *n) for n in tree))
        offsets = []
        for s, lfmt in self._strings():
            if s is None:
                offsets.append(NULL)
                continue
            data = s.encode("utf-8")
            limit = 0xFF if lfmt == ">B" else 0xFFFF
            if len(data) > limit:
                raise ValueError(f"문자열 {len(data)} B > {limit}: {s[:30]!r}")
            offsets.append(len(area))
            area += struct.pack(lfmt, len(data)) + _encode(data, codes)
        out = bytearray(self.header)
        for i, r in enumerate(self.rows):
            out += REC.pack(offsets[2 * i], offsets[2 * i + 1], r.hashid, r.extra)
        out += area
        struct.pack_into(">I", out, 0x30, len(area))
        out += bytes(-len(out) % 8) + bytes(4)
        struct.pack_into(">I", out, 0x08, len(out))
        for at, s, e in _crc_targets(out):
            struct.pack_into(">I", out, at, crc32_mpeg2(out[s:e]))
        return bytes(out)
