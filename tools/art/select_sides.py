"""진영 선택 화면 "SELECT SIDES" 텍스처(256x256, RGB 0 + 알파 무늬)의 한글판 생성.

가로로 번진 노이즈(붓 질감)를 글자 마스크에 곱해 원본 VS 와 비슷한 질감을 낸다.
사용: python tools/art/select_sides.py <원본 SELECT 텍스처 PNG> <출력 PNG>
"""
import sys
from pathlib import Path

import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "work" / "fonts" / "BlackHanSans-Regular.ttf"
LINES = ("진영", "선택")


def text_mask(size, box, stretch=1.3):
    """box(x0, y0, x1, y1) 안에 두 줄을 그린 L 마스크. 줄 높이에 맞춘 뒤 가로로 최대 stretch 배 늘린다."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    gap = int(h * 0.06)
    line_h = (h - gap) // 2
    mask = Image.new("L", size, 0)
    for i, line in enumerate(LINES):
        font = ImageFont.truetype(str(FONT), line_h * 2)
        l, t, r, b = font.getbbox(line)
        glyph = Image.new("L", (r - l, b - t), 0)
        ImageDraw.Draw(glyph).text((-l, -t), line, font=font, fill=255)
        scale = line_h / glyph.height
        gw = min(w, int(glyph.width * scale * stretch))
        glyph = glyph.resize((gw, line_h), Image.LANCZOS)
        mask.paste(glyph, (x0 + (w - gw) // 2, y0 + i * (line_h + gap)))
    return mask


def grunge(size, seed=7):
    """가로 붓자국 + 얼룩 질감 (알파 140~255)."""
    random.seed(seed)
    w, h = size
    streak = Image.effect_noise((w // 8, h), 64).resize((w, h), Image.BICUBIC)  # 가로로 늘인 노이즈
    blot = Image.effect_noise((w // 16, h // 16), 80).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    g = ImageChops.multiply(streak, blot.point(lambda v: 128 + v // 2))
    lo, hi = g.getextrema()
    g = g.point(lambda v: int(140 + 115 * (v - lo) / max(1, hi - lo)))
    d = ImageDraw.Draw(g)
    for _ in range(14):  # 작은 긁힘·점
        x, y, r = random.randrange(w), random.randrange(h), random.randrange(2, 5)
        d.ellipse((x - r, y - r, x + r, y + r), fill=random.choice((70, 200)))
    return g


def main():
    sel, out = (Path(a) for a in sys.argv[1:3])
    orig = Image.open(sel).convert("RGBA")
    a = orig.split()[3]
    bbox = a.point(lambda v: 255 if v > 16 else 0).getbbox()  # 원래 글자가 차지하던 영역
    mask = text_mask(orig.size, bbox)
    alpha = ImageChops.multiply(mask, grunge(orig.size))
    res = Image.merge("RGBA", (Image.new("L", orig.size, 0),) * 3 + (alpha,))
    res.save(out)
    print(out, "글자 영역", bbox)


if __name__ == "__main__":
    main()
