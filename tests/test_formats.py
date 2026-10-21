import pytest

from fnc import chunkzip, eb, t3db

LOC_DBS = [
    "data/ps3/loc/eng/database/eng_us.db",
    "data/ps3/loc/fre/database/fre_fr.db",
    "data/ps3/loc/ger/database/ger_de.db",
    "data/ps3/loc/lng/database/lng_lg.db",
]


# --- CRC ---------------------------------------------------------------

def test_crc_mpeg2_check_value():
    assert t3db.crc32_mpeg2(b"123456789") == 0x0376E6E7


# --- EB archive --------------------------------------------------------

def test_eb_lists_loc_databases(boot_big):
    arc = eb.Archive.parse(boot_big)
    assert len(arc.entries) == 26
    assert set(LOC_DBS) <= {e.path for e in arc.entries}


def test_eb_rebuild_unchanged_is_identical(boot_big):
    arc = eb.Archive.parse(boot_big)
    assert arc.build() == boot_big


def test_eb_replace_grows_file_and_keeps_others(boot_big):
    arc = eb.Archive.parse(boot_big)
    target = "data/ps3/loc/eng/database/eng_us.db"
    new = b"X" * (len(arc.read(target)) + 12345)
    out = eb.Archive.parse(arc.replaced({target: new}).build())
    assert out.read(target) == new
    for e in arc.entries:
        if e.path != target:
            assert out.read(e.path) == arc.read(e.path)


def test_eb_replace_unknown_path_fails(boot_big):
    arc = eb.Archive.parse(boot_big)
    with pytest.raises(KeyError):
        arc.replaced({"no/such/file": b""})


# --- chunkzip ----------------------------------------------------------

@pytest.mark.parametrize("path", LOC_DBS)
def test_chunkzip_unpack_matches_declared_size(boot_big, path):
    packed = eb.Archive.parse(boot_big).read(path)
    raw = chunkzip.unpack(packed)
    assert raw[:4] == b"DB\x00\x08"
    assert len(raw) == chunkzip.declared_size(packed)


def test_chunkzip_pack_roundtrip():
    data = bytes(range(256)) * 3000  # 768000 B → 여러 청크
    packed = chunkzip.pack(data)
    assert packed[:8] == b"chunkzip"
    assert chunkzip.unpack(packed) == data


@pytest.mark.parametrize("path", LOC_DBS)
def test_chunkzip_pack_of_real_db_roundtrip(boot_big, path):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(path))
    assert chunkzip.unpack(chunkzip.pack(raw)) == raw


# --- T3DB --------------------------------------------------------------

@pytest.mark.parametrize("path", LOC_DBS)
def test_t3db_reencode_with_original_tree_is_identical(boot_big, path):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(path))
    db = t3db.LanguageDB.parse(raw)
    assert len(db.rows) == 10019
    assert db.build(tree=db.tree) == raw


def test_t3db_decodes_known_row(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    db = t3db.LanguageDB.parse(raw)
    row = db.by_id()["TXT_DIAMOND_CHIN"]
    assert row.text == "Diamond Chin"
    assert row.hashid == 1332426


def test_t3db_null_text_preserved(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    db = t3db.LanguageDB.parse(raw)
    assert sum(r.text is None for r in db.rows) == 36
    again = t3db.LanguageDB.parse(db.build())
    assert [r.text for r in again.rows] == [r.text for r in db.rows]


def test_t3db_korean_text_roundtrip_with_new_tree(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    db = t3db.LanguageDB.parse(raw)
    ko = "다이아몬드 턱\n%1s 님이 %2d 라운드에 승리!"
    edited = db.with_texts({"TXT_DIAMOND_CHIN": ko})
    out = edited.build()
    again = t3db.LanguageDB.parse(out)
    assert again.by_id()["TXT_DIAMOND_CHIN"].text == ko
    assert [r.text for r in again.rows if r.stringid != "TXT_DIAMOND_CHIN"] == [
        r.text for r in db.rows if r.stringid != "TXT_DIAMOND_CHIN"
    ]
    assert t3db.verify_crcs(out) == []


def test_t3db_original_crcs_verify(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    assert t3db.verify_crcs(raw) == []


def test_t3db_text_length_limit(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    db = t3db.LanguageDB.parse(raw)
    with pytest.raises(ValueError):
        db.with_texts({"TXT_DIAMOND_CHIN": "가" * 22000}).build()  # 66000 B > u16


def test_t3db_unknown_id_fails(boot_big):
    raw = chunkzip.unpack(eb.Archive.parse(boot_big).read(LOC_DBS[0]))
    db = t3db.LanguageDB.parse(raw)
    with pytest.raises(KeyError):
        db.with_texts({"NO_SUCH_ID": "x"})


def test_eb_rejects_overlapping_entries(boot_big):
    import struct
    raw = bytearray(boot_big)
    off0, _, size0, _ = struct.unpack_from(">IIII", raw, 0x30)
    off1, z, size1, h = struct.unpack_from(">IIII", raw, 0x40)
    struct.pack_into(">IIII", raw, 0x40, off0, z, size1, h)  # 엔트리 1을 엔트리 0과 같은 위치로
    with pytest.raises(ValueError):
        eb.Archive.parse(bytes(raw))


def test_eb_rejects_entry_past_end(boot_big):
    import struct
    raw = bytearray(boot_big)
    off, z, size, h = struct.unpack_from(">IIII", raw, 0x30)
    struct.pack_into(">IIII", raw, 0x30, off, z, len(raw), h)
    with pytest.raises(ValueError):
        eb.Archive.parse(bytes(raw))
