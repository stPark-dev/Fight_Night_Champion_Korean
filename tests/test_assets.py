import io
import struct
from pathlib import Path

import pytest
from PIL import Image

import build
from fnc import bigf, dxt, eb, refpack

ROOT = Path(__file__).resolve().parents[1]
FE_BIG = ROOT / "work/extract/PS3_GAME/USRDIR/databigs/ps3/fe.big"


def test_refpack_literal_roundtrip():
    for n in (0, 1, 3, 4, 111, 112, 113, 1000, 4097):
        data = bytes((i * 7) & 0xFF for i in range(n))
        packed = refpack.pack_literal(data)
        assert refpack.is_refpack(packed) or n == 0
        assert refpack.unpack(packed) == data


def test_dxt5_encode_shape_and_alpha():
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (0, 0, 4, 4))
    data = dxt.encode_dxt5(img)
    assert len(data) == 4 * 16
    assert data[0] == 255 and data[1] == 255  # 첫 블록 알파 끝점
    assert data[16] == 0 and data[17] == 0    # 둘째 블록은 투명


@pytest.fixture(scope="module")
def fe_arc():
    if not FE_BIG.exists():
        pytest.skip("원본 추출본 없음: work/extract")
    return eb.Archive.parse(FE_BIG.read_bytes())


def test_bigf_roundtrip_sample(fe_arc):
    paths = [e.path for e in fe_arc.entries if e.path.endswith(".big")][::200]
    for p in paths:
        raw = fe_arc.read(p)
        assert bigf.Bigf.parse(raw).build() == raw, p


def test_image_manifest_applies(fe_arc):
    files = build.image_files(fe_arc)
    assert files
    for big, raw in files.items():
        nested = {e.name: e.data for e in bigf.Bigf.parse(raw).entries}
        orig = {e.name: e.data for e in bigf.Bigf.parse(fe_arc.read(big)).entries}
        changed = [k for k in nested if nested[k] != orig[k]]
        assert changed
        for k in changed:
            dds = refpack.unpack(nested[k])
            im = Image.open(io.BytesIO(dds))
            assert im.size == struct.unpack_from("<II", dds, 16)[::-1] or im.size
