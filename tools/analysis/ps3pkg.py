"""PS3 retail PKG 목록/추출 (분석 전용). 사용: python ps3pkg.py <pkg> [출력폴더]
형식: 헤더 0xC0, 데이터는 AES-128-CTR(키 = PS3 공개 PKG 키, 카운터 = 헤더 0x70 의 16바이트).
"""
import os
import struct
import sys

from Crypto.Cipher import AES
from Crypto.Util import Counter

PS3_KEY = bytes.fromhex("2E7B71D7C9C9A14EA3221F188828B8F8")


def open_pkg(path):
    f = open(path, "rb")
    h = f.read(0xC0)
    if h[:4] != b"\x7fPKG":
        raise ValueError("PKG 아님")
    rev, typ = struct.unpack_from(">HH", h, 4)
    if typ != 1:
        raise ValueError(f"PS3 PKG 아님 (type {typ})")
    item_count, total, data_off, data_size = struct.unpack_from(">IQQQ", h, 0x14)
    iv = int.from_bytes(h[0x70:0x80], "big")

    def read(off, size):
        f.seek(data_off + off)
        raw = f.read(size)
        blk = off // 16
        ctr = Counter.new(128, initial_value=(iv + blk) & ((1 << 128) - 1))
        c = AES.new(PS3_KEY, AES.MODE_CTR, counter=ctr)
        pad = off % 16
        return c.decrypt(b"\0" * pad + raw)[pad:]

    return h, item_count, read


def items(path):
    h, n, read = open_pkg(path)
    table = read(0, n * 32)
    out = []
    for i in range(n):
        noff, nsize, doff, dsize, flags = struct.unpack_from(">IIQQI", table, i * 32)
        name = read(noff, nsize).decode("utf-8", "replace")
        out.append((name, doff, dsize, flags & 0xFF))
    return out, read


if __name__ == "__main__":
    lst, read = items(sys.argv[1])
    dest = sys.argv[2] if len(sys.argv) > 2 else None
    for name, off, size, kind in lst:
        print(f"{size:>12}  type={kind:#x}  {name}")
        if dest and kind not in (4,):  # 4 = 폴더
            p = os.path.join(dest, name)
            if os.path.commonpath([os.path.abspath(dest), os.path.abspath(p)]) != os.path.abspath(dest):
                raise ValueError(f"PKG 항목 경로가 출력 폴더 밖을 가리킴: {name}")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as o:
                pos = 0
                while pos < size:
                    n = min(1 << 22, size - pos)
                    o.write(read(off + pos, n)); pos += n
