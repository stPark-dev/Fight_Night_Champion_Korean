import io
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from build import DEFAULT_HANGUL_FONT
from fnc import fontmerge

ROOT = Path(__file__).resolve().parents[1]
GAME_FONT = ROOT / "work/fe/data/ps3/fe/fonts/eahelveticaneueconbol-mod.ttf"
HANGUL_SRC = DEFAULT_HANGUL_FONT
CHARS = "시작버튼을누르세요"


@pytest.fixture(scope="module")
def merged():
    if not GAME_FONT.exists() or not HANGUL_SRC.exists():
        pytest.skip("폰트 원본 없음")
    base = GAME_FONT.read_bytes()
    out = fontmerge.merge(base, HANGUL_SRC.read_bytes(), CHARS)
    return TTFont(io.BytesIO(base)), TTFont(io.BytesIO(out)), out


def test_new_codepoints_mapped_in_unicode_cmaps(merged):
    _, new, _ = merged
    for sub in new["cmap"].tables:
        if sub.isUnicode():
            for ch in CHARS:
                assert ord(ch) in sub.cmap, (sub.platformID, sub.platEncID, ch)


def test_original_glyphs_unchanged(merged):
    old, new, _ = merged
    for name in old.getGlyphOrder():
        assert new["glyf"][name].compile(new["glyf"]) == old["glyf"][name].compile(old["glyf"])
        assert new["hmtx"][name] == old["hmtx"][name]
    for sub in old["cmap"].tables:
        assert all(new["cmap"].getcmap(sub.platformID, sub.platEncID).cmap[c] == g
                   for c, g in sub.cmap.items())


def test_glyph_count_and_metrics(merged):
    old, new, _ = merged
    assert new["maxp"].numGlyphs == old["maxp"].numGlyphs + len(set(CHARS))
    cmap = new.getBestCmap()
    for ch in CHARS:
        g = new["glyf"][cmap[ord(ch)]]
        adv, _ = new["hmtx"][cmap[ord(ch)]]
        assert g.numberOfContours > 0 and adv > 0


def test_hangul_height_follows_cap_height(merged):
    _, new, _ = merged
    cmap = new.getBestCmap()
    cap = new["glyf"]["H"].yMax
    g = new["glyf"][cmap[ord("시")]]
    assert 0.9 * cap <= g.yMax - min(0, g.yMin) <= 1.3 * cap


def test_reloads_after_compile(merged):
    _, _, out = merged
    font = TTFont(io.BytesIO(out))
    font["glyf"]  # 전체 테이블 디컴파일 가능
    assert font["hdmx"].hdmx  # hdmx 테이블 일관성 유지


def test_missing_source_glyph_fails():
    if not GAME_FONT.exists() or not HANGUL_SRC.exists():
        pytest.skip("폰트 원본 없음")
    with pytest.raises(KeyError):
        fontmerge.merge(GAME_FONT.read_bytes(), HANGUL_SRC.read_bytes(), "\U0001F600")


def test_existing_codepoint_not_overridden():
    if not GAME_FONT.exists() or not HANGUL_SRC.exists():
        pytest.skip("폰트 원본 없음")
    base = GAME_FONT.read_bytes()
    out = TTFont(io.BytesIO(fontmerge.merge(base, HANGUL_SRC.read_bytes(), "A가")))
    assert out.getBestCmap()[ord("A")] == TTFont(io.BytesIO(base)).getBestCmap()[ord("A")]


def test_merge_is_deterministic():
    if not GAME_FONT.exists() or not HANGUL_SRC.exists():
        pytest.skip("폰트 원본 없음")
    import time
    base, src = GAME_FONT.read_bytes(), HANGUL_SRC.read_bytes()
    a = fontmerge.merge(base, src, CHARS)
    time.sleep(1.1)
    assert fontmerge.merge(base, src, CHARS) == a


def test_existing_unmapped_glyph_name_rejected():
    if not GAME_FONT.exists() or not HANGUL_SRC.exists():
        pytest.skip("폰트 원본 없음")
    src = HANGUL_SRC.read_bytes()
    font = TTFont(io.BytesIO(fontmerge.merge(GAME_FONT.read_bytes(), src, "가")))
    for sub in font["cmap"].tables:
        sub.cmap.pop(0xAC00, None)  # 글리프 uniAC00 은 남기고 매핑만 제거
    buf = io.BytesIO()
    font.save(buf)
    with pytest.raises(ValueError):
        fontmerge.merge(buf.getvalue(), src, "가")
