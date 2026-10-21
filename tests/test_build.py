import io
import json
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
