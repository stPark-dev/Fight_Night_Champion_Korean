"""게임 TTF에 한글 글리프 병합.

원본 글리프·메트릭·cmap 항목은 그대로 두고, 요청 문자만 새 글리프로 추가한다.
크기는 원본 'H' 높이(캡 하이트) 비율로 맞추고, 새 글리프에는 힌팅 명령을 넣지 않는다.
simplify(폰트 단위 허용 오차)를 주면 윤곽을 2차→3차→2차 곡선으로 다시 근사해 점 수를 줄인다
(게임 메모리가 빠듯해 폰트 크기를 줄여야 함 — docs/freeze_investigation.md).
"""
import io

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

HANGUL_SCALE = 1.1
BASELINE_DROP = 0.04


def _cap_height(font):
    return font["glyf"]["H"].yMax if "glyf" in font else font["OS/2"].sCapHeight


def merge(base_bytes, source_bytes, chars, simplify=0):
    base = TTFont(io.BytesIO(base_bytes), recalcTimestamp=False)  # 재현 가능한 빌드
    src = TTFont(io.BytesIO(source_bytes))
    src_cmap = src.getBestCmap()
    base_cmap = base.getBestCmap()
    todo = sorted({ord(c) for c in chars} - set(base_cmap))
    missing = [hex(cp) for cp in todo if cp not in src_cmap]
    if missing:
        raise KeyError(f"원본 폰트에 없는 문자: {missing}")

    src_glyphs = src.getGlyphSet()
    # 기준 글자 '한'의 높이 = 캡 하이트 × HANGUL_SCALE, 바닥은 베이스라인 약간 아래
    ref = src["glyf"][src_cmap[ord("한")]]
    cap = _cap_height(base)
    s = cap * HANGUL_SCALE / (ref.yMax - ref.yMin)
    dy = -ref.yMin * s - cap * BASELINE_DROP
    order = list(base.getGlyphOrder())
    glyf, hmtx = base["glyf"], base["hmtx"]
    hdmx = None
    if "hdmx" in base:
        hdmx = base["hdmx"].hdmx = {ppem: dict(w.items()) for ppem, w in base["hdmx"].hdmx.items()}
    ltsh = base["LTSH"].yPels if "LTSH" in base else None
    upm = base["head"].unitsPerEm

    existing = set(base.getGlyphOrder())
    for cp in todo:
        name = f"uni{cp:04X}"
        if name in existing:
            raise ValueError(f"원본 폰트에 매핑 안 된 같은 이름 글리프가 있음: {name}")
        rec = DecomposingRecordingPen(src_glyphs)
        src_glyphs[src_cmap[cp]].draw(rec)
        pen = TTGlyphPen(None)
        if simplify:
            cubic = RecordingPen()
            rec.replay(TransformPen(Qu2CuPen(cubic, max_err=simplify, all_cubic=True), (s, 0, 0, s, 0, dy)))
            cubic.replay(Cu2QuPen(pen, max_err=simplify, reverse_direction=False))
        else:
            rec.replay(TransformPen(pen, (s, 0, 0, s, 0, dy)))
        g = pen.glyph()
        g.recalcBounds(glyf)
        adv = round(src["hmtx"][src_cmap[cp]][0] * s)
        order.append(name)
        glyf[name] = g
        hmtx[name] = (adv, getattr(g, "xMin", 0))
        if hdmx is not None:
            for ppem, widths in hdmx.items():
                widths[name] = round(adv * ppem / upm)
        if ltsh is not None:
            ltsh[name] = 1
        for sub in base["cmap"].tables:
            if sub.isUnicode() and sub.format == 4:
                sub.cmap[cp] = name

    base.setGlyphOrder(order)
    glyf.glyphOrder = order
    out = io.BytesIO()
    base.save(out)
    unmapped = set(todo) - set(TTFont(io.BytesIO(out.getvalue())).getBestCmap())
    if unmapped:
        raise ValueError(f"유니코드 cmap(형식 4)에 매핑되지 않음: {sorted(map(hex, unmapped))[:5]}")
    return out.getvalue()
