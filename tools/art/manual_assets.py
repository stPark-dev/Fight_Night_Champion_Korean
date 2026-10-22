"""설명서 렌더링 재료를 사용자의 원본 fe.big 에서 만든다(저장소에는 게임 그림을 두지 않음).

  work/manual/src/eng_<N>.png   원본 영어 쪽(1024x1024)
  work/manual/background.png    글자 없는 배경(본문 쪽 중앙값 + 남은 글자 인페인팅)
  work/manual/icons/<버튼>.png  원본 쪽에서 잘라 낸 버튼 아이콘

사용: python tools/art/manual_assets.py
"""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from fnc import bigf, eb, refpack  # noqa: E402

FE_BIG = ROOT / "work" / "extract" / "PS3_GAME" / "USRDIR" / "databigs" / "ps3" / "fe.big"
OUT = ROOT / "work" / "manual"
PAGE = "data/ps3/fe/artassets/manual_ps3/manual_ps3_eng_{}.big"
PAGES = 25
W, H = 960, 540
# (쪽, x, y, w, h): 원본 쪽에서 버튼 아이콘 위치
ICONS = {"R": (5, 109, 110, 39, 39), "L1": (5, 549, 113, 46, 31), "R2": (5, 700, 315, 42, 41),
         "TRIANGLE": (2, 575, 374, 43, 44), "CIRCLE": (2, 665, 374, 43, 44), "SQUARE": (2, 575, 425, 43, 44),
         "CROSS": (2, 665, 425, 43, 44), "L2": (2, 574, 475, 47, 47)}
# 모든 쪽 공통 위치에 남는 글자(제목줄·머리글·쪽 번호·별)
FILL = [(50, 68, 260, 110), (50, 118, 70, 175), (820, 12, 950, 40), (910, 490, 945, 520), (24, 70, 54, 108)]


def page_image(arc, n):
    entries = {e.name: e.data for e in bigf.Bigf.parse(arc.read(PAGE.format(n))).entries}
    dds = entries["2"]
    if refpack.is_refpack(dds):
        dds = refpack.unpack(dds)
    return Image.open(io.BytesIO(dds)).convert("RGBA")


def background(pages):
    import cv2
    body = [np.asarray(p.convert("RGB"))[:H, :W] for i, p in enumerate(pages) if i >= 5]
    gray = np.stack([cv2.cvtColor(a, cv2.COLOR_RGB2GRAY) for a in body]).astype(np.int16)
    text = (gray - np.median(gray, axis=0)) > 40           # 글자 픽셀은 빼고
    rgb = np.stack(body).astype(np.float32)
    clean = np.nanmedian(np.where(text[..., None], np.nan, rgb), axis=0)
    im = np.nan_to_num(clean).astype(np.uint8)
    g = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    mask = np.zeros(g.shape, np.uint8)
    for x0, y0, x1, y1 in FILL:
        mask[y0:y1, x0:x1] = (g[y0:y1, x0:x1] > 45) * 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    out = cv2.inpaint(cv2.cvtColor(im, cv2.COLOR_RGB2BGR), mask, 7, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def prepare(fe_big=FE_BIG):
    arc = eb.Archive.parse(Path(fe_big).read_bytes())
    (OUT / "src").mkdir(parents=True, exist_ok=True)
    (OUT / "icons").mkdir(exist_ok=True)
    pages = []
    for n in range(PAGES):
        im = page_image(arc, n)
        im.save(OUT / "src" / f"eng_{n}.png")
        pages.append(im)
    background(pages).save(OUT / "background.png")
    for name, (n, x, y, w, h) in ICONS.items():
        pages[n].crop((x - 2, y - 2, x + w + 2, y + h + 2)).save(OUT / "icons" / f"{name}.png")
    return OUT


if __name__ == "__main__":
    print(prepare())
