import io
import json
import struct
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

import build
from fnc import chunkzip, eb, t3db

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "work" / "extract"
HANGUL_SRC = build.DEFAULT_HANGUL_FONT
POC = {"TXT_PRESS_START_LINE_1": "START 버튼을", "TXT_PRESS_START_LINE_2": "누르세요"}


@pytest.fixture(scope="module")
def outputs():
    if not EXTRACT.exists() or not HANGUL_SRC.exists():
        pytest.skip("원본 추출본/폰트 없음")
    return build.build_files(EXTRACT, POC, HANGUL_SRC)


def test_outputs_are_only_the_two_archives(outputs):
    assert set(outputs) == {build.BOOT_BIG, build.FE_BIG}


def test_db_contains_translation_and_keeps_rest(outputs):
    arc = eb.Archive.parse(outputs[build.BOOT_BIG])
    db = t3db.LanguageDB.parse(chunkzip.unpack(arc.read(build.ENG_DB)))
    orig = t3db.LanguageDB.parse(chunkzip.unpack(
        eb.Archive.parse((EXTRACT / build.BOOT_BIG).read_bytes()).read(build.ENG_DB)))
    ids = db.by_id()
    for k, v in POC.items():
        assert ids[k].text == v
    assert [(r.stringid, r.text) for r in db.rows if r.stringid not in POC] == \
        [(r.stringid, r.text) for r in orig.rows if r.stringid not in POC]


def test_every_ui_font_covers_translated_chars(outputs):
    arc = eb.Archive.parse(outputs[build.FE_BIG])
    fonts = [e.path for e in arc.entries if e.path.startswith(build.FONT_DIR) and e.path.endswith(".ttf")]
    assert len(fonts) == 8
    need = {ord(c) for v in POC.values() for c in v}
    for p in fonts:
        cmap = TTFont(io.BytesIO(arc.read(p))).getBestCmap()
        assert need <= set(cmap), p


def test_unknown_string_id_fails():
    if not EXTRACT.exists():
        pytest.skip("원본 추출본 없음")
    with pytest.raises(KeyError):
        build.build_files(EXTRACT, {"NO_SUCH_ID": "가"}, HANGUL_SRC)


def test_load_translations_rejects_non_string(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"TXT_A": 3}), encoding="utf-8")
    with pytest.raises(ValueError):
        build.load_translations(p)


def test_materialize_links_unchanged_and_writes_changed(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "a" / "keep.bin").write_bytes(b"keep")
    (src / "a" / "change.bin").write_bytes(b"old")
    out = tmp_path / "out"
    build.materialize(src, out, {"a/change.bin": b"new"})
    assert (out / "a" / "keep.bin").read_bytes() == b"keep"
    assert (out / "a" / "change.bin").read_bytes() == b"new"
    assert (src / "a" / "change.bin").read_bytes() == b"old"  # 원본 불변


def test_english_subtitles_generated_from_french():
    if not EXTRACT.exists():
        pytest.skip("원본 추출본 없음")
    subs = build.english_subtitles(EXTRACT)
    fre = sorted((EXTRACT / build.FMV_DIR).glob("*_fre.sub"))
    assert len(subs) == len(fre) == 36
    for f in fre:
        rel = f"{build.FMV_DIR}/{f.name[:-len('_fre.sub')]}_eng.sub"
        assert subs[rel] == f.read_bytes()


# --- 리뷰 반영 ---------------------------------------------------------

def test_load_translations_rejects_duplicate_keys(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"TXT_A": "가", "TXT_A": "나"}', encoding="utf-8")
    with pytest.raises(ValueError):
        build.load_translations(p)


def test_load_translations_merges_directory(tmp_path):
    (tmp_path / "a.json").write_text('{"A": "가"}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"B": "나"}', encoding="utf-8")
    assert build.load_translations(tmp_path) == {"A": "가", "B": "나"}
    (tmp_path / "c.json").write_text('{"A": "다"}', encoding="utf-8")
    with pytest.raises(ValueError, match="중복 키 A"):
        build.load_translations(tmp_path)


def test_load_translations_rejects_non_object(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('["가"]', encoding="utf-8")
    with pytest.raises(ValueError):
        build.load_translations(p)


def test_token_mismatch_fails():
    # 원문: "Diamond Chin" (토큰 없음) / "%1s %2s %3s"
    orig = {"A": "Load %1s <0>{c0}", "B": "%1s %2s %3s"}
    assert build.token_mismatches({"A": "%1s <0>{c0} 불러오기"}, orig) == []
    assert build.token_mismatches({"A": "%1d <0>{c0} 불러오기"}, orig) == ["A"]
    assert build.token_mismatches({"A": "%1s 불러오기"}, orig) == ["A"]
    assert build.token_mismatches({"B": "%3s %1s %2s"}, orig) == []


def test_token_kinds():
    orig = {"S": "%PUNCHER landed a %HAND to %PUNCHEE’s %TARGET", "T": "%dRD %d:%.2d",
            "U": "Use ^LT^ or ^RT^", "V": "Win %"}
    assert build.token_mismatches({"S": "%PUNCHER의 %HAND, %PUNCHEE의 %TARGET에 적중"}, orig) == []
    assert build.token_mismatches({"S": "%PUNCHER의 %HAND 적중"}, orig) == ["S"]
    assert build.token_mismatches({"T": "%dR %d:%d"}, orig) == ["T"]
    assert build.token_mismatches({"U": "^LT^ 또는 ^RT^ 사용"}, orig) == []
    assert build.token_mismatches({"U": "^LT^ 사용"}, orig) == ["U"]
    assert build.token_mismatches({"V": "승률 %"}, orig) == []


def test_build_files_rejects_token_mismatch():
    if not EXTRACT.exists():
        pytest.skip("원본 추출본 없음")
    with pytest.raises(ValueError):
        build.build_files(EXTRACT, {"TXT_SPEV_BOXER_TYPE": "%1s %2s"}, HANGUL_SRC)


@pytest.mark.parametrize("rel", [".", "src", "src/inner", ".."])
def test_materialize_refuses_overlapping_out(tmp_path, rel):
    src = tmp_path / "src"
    (src / "inner").mkdir(parents=True)
    (src / "a.bin").write_bytes(b"x")
    with pytest.raises(ValueError):
        build.materialize(src, (src / rel) if rel != "src" else src, {})
    assert (src / "a.bin").read_bytes() == b"x"


def test_english_subtitles_fail_when_none(tmp_path):
    (tmp_path / build.FMV_DIR).mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        build.english_subtitles(tmp_path)


def test_english_subtitles_refuse_existing_target(tmp_path):
    fmv = tmp_path / build.FMV_DIR
    fmv.mkdir(parents=True)
    (fmv / "mm_1_fre.sub").write_bytes(b"f")
    (fmv / "mm_1_eng.sub").write_bytes(b"e")
    with pytest.raises(FileExistsError):
        build.english_subtitles(tmp_path)


def test_ascii_chars_also_checked_against_fonts():
    assert build.needed_chars({"A": "a~가\n", "B": "|"}) == "a|~가"


# --- 지역판 일치 --------------------------------------------------------

EXTRACT_US = ROOT / "work" / "extract_us"
ELF_JP = ROOT / "work" / "eboot" / "EBOOT.elf"
ELF_US = ROOT / "work" / "eboot_us" / "EBOOT.elf"


@pytest.mark.parametrize("extract,title", [(EXTRACT, "BLJM60267"), (EXTRACT_US, "BLUS30608")])
def test_title_id_from_param_sfo(extract, title):
    if not extract.exists():
        pytest.skip("추출본 없음")
    assert build.title_id(extract) == title


@pytest.mark.parametrize("extract,elf", [(EXTRACT, ELF_US), (EXTRACT_US, ELF_JP)])
def test_region_mismatch_fails(extract, elf):
    if not extract.exists() or not elf.exists():
        pytest.skip("추출본/EBOOT 없음")
    with pytest.raises(ValueError):
        build.build_eboot(elf, extract)


@pytest.mark.parametrize("extract,elf", [(EXTRACT, ELF_JP), (EXTRACT_US, ELF_US)])
def test_region_match_builds(extract, elf):
    if not extract.exists() or not elf.exists():
        pytest.skip("추출본/EBOOT 없음")
    assert build.build_eboot(elf, extract)[:4] == b"\x7fELF"


# --- 타이틀 업데이트 1.02 -----------------------------------------------

UPD = {"BLJM60267": ROOT / "work/updates/jp_102", "BLUS30608": ROOT / "work/updates/us_102"}
UPD_ELF = {"BLJM60267": ROOT / "work/eboot_jp102/EBOOT.elf", "BLUS30608": ROOT / "work/eboot_us102/EBOOT.elf"}
DLC_ID = "TXT_BARE_KNUCKLES_MODE"


def _need_update(title):
    if not UPD[title].exists() or not UPD_ELF[title].exists():
        pytest.skip(f"{title} 1.02 업데이트 추출본/복호화 EBOOT 없음")


def test_disc_build_accepts_dlc_only_ids_when_declared():
    if not EXTRACT.exists() or not HANGUL_SRC.exists():
        pytest.skip("원본 추출본/폰트 없음")
    tr = {**POC, DLC_ID: "맨주먹 모드"}
    with pytest.raises(KeyError):
        build.build_files(EXTRACT, tr, HANGUL_SRC)
    files = build.build_files(EXTRACT, tr, HANGUL_SRC, extra_ids={DLC_ID})
    db = t3db.LanguageDB.parse(chunkzip.unpack(eb.Archive.parse(files[build.BOOT_BIG]).read(build.ENG_DB)))
    assert DLC_ID not in db.by_id()


@pytest.fixture(scope="module")
def translations_ko():
    return build.load_translations(ROOT / "translations/ko")


@pytest.mark.parametrize("title", ["BLJM60267", "BLUS30608"])
def test_build_update(title, translations_ko):
    _need_update(title)
    files = build.build_update(UPD[title], UPD_ELF[title], translations_ko)
    us = title == "BLUS30608"
    sfx = ".edat" if us else ""
    main, toc = f"USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big{sfx}", f"USRDIR/dlc_pack1/dlc.toc{sfx}"
    assert set(files) == {"USRDIR/EBOOT.BIN", main, toc}
    assert files["USRDIR/EBOOT.BIN"][:4] == b"\x7fELF"
    from fnc import edat
    plain = (lambda b: edat.decrypt(b, edat.FNC_KLIC)) if us else (lambda b: b)
    big = plain(files[main])
    arc = eb.Archive.parse(big)
    db = t3db.LanguageDB.parse(chunkzip.unpack(arc.read(build.ENG_DB))).by_id()
    assert db[DLC_ID].text == "맨주먹 모드"
    assert db["TXT_PRESS_START_LINE_2"].text == translations_ko["TXT_PRESS_START_LINE_2"]
    # dlc.toc 의 dlc_main.big 크기가 새 크기
    sizes = [struct.unpack_from(">I", plain(files[toc]), 0x10 + 12 * i + 8)[0] for i in range(4)]
    assert len(big) in sizes
    # 진영 선택 그림도 DLC 쪽에서 교체
    orig = eb.Archive.parse(plain((UPD[title] / main).read_bytes()))
    sel = "data/ps3/fe/game/screens/playnow/01_boxerselect.big"
    assert arc.read(sel) != orig.read(sel)


def test_update_dlc_same_plaintext_both_regions(translations_ko):
    _need_update("BLJM60267"), _need_update("BLUS30608")
    from fnc import edat
    jp = build.build_update(UPD["BLJM60267"], UPD_ELF["BLJM60267"], translations_ko)
    us = build.build_update(UPD["BLUS30608"], UPD_ELF["BLUS30608"], translations_ko)
    assert edat.decrypt(us["USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big.edat"], edat.FNC_KLIC) == \
        jp["USRDIR/dlc_pack1/dlc/data/ps3/dlc_main.big"]


def test_param_sfo_reads_update_version():
    if not UPD["BLJM60267"].exists():
        pytest.skip("업데이트 추출본 없음")
    info = build.param_sfo(UPD["BLJM60267"] / "PARAM.SFO")
    assert info["TITLE_ID"] == "BLJM60267" and info["APP_VER"] == "01.02"


def test_build_update_rejects_non_102_folder(tmp_path, translations_ko):
    _need_update("BLJM60267")
    import shutil
    fake = tmp_path / "upd"
    shutil.copytree(UPD["BLJM60267"], fake, copy_function=lambda s, d: shutil.copy(s, d))
    sfo = bytearray((fake / "PARAM.SFO").read_bytes())
    i = sfo.index(b"01.02")
    sfo[i:i + 5] = b"01.01"
    (fake / "PARAM.SFO").write_bytes(bytes(sfo))
    with pytest.raises(ValueError):
        build.build_update(fake, UPD_ELF["BLJM60267"], translations_ko)
