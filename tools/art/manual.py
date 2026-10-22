"""게임 설명서(메인 메뉴 □) 한글 쪽 렌더러.

입력: assets/manual/manual.json (쪽별 한국어 원고·배치), work/manual/(manual_assets.py 가 원본에서 만든
      배경·아이콘·원본 쪽 — 게임 그림이라 저장소에 두지 않음)
출력: work/manual/pages/ko_<N>.png (1024x1024, 내용은 왼쪽 위 960x540) — build 가 DDS 로 바꿔 넣는다.

사용: python tools/art/manual.py [--pages 5,6]
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "manual"
GEN = ROOT / "work" / "manual"
FONT_BODY = ROOT / "work" / "fonts" / "NanumGothic-Bold.ttf"
FONT_HEAD = ROOT / "work" / "fonts" / "BlackHanSans-Regular.ttf"
SRC = GEN / "src" / "eng_{}.png"
W, H = 960, 540
YELLOW = (228, 180, 38)
WHITE = (236, 236, 236)
GREY = (170, 170, 170)
LEFT, RIGHT = 53, 935
TOKEN = re.compile(r"\{([A-Z0-9_]+)\}")
SYMBOL = {"TRIANGLE": "△", "CIRCLE": "○", "CROSS": "✕", "SQUARE": "□", "UP": "↑", "DOWN": "↓",
          "LEFT": "←", "RIGHT": "→", "L_LEFT": "L←", "L_RIGHT": "L→", "R_UP": "R↑", "DPAD": "+"}


def font(path, size):
    return ImageFont.truetype(str(path), size)


def icon(name, h):
    """버튼 아이콘(높이 h). 잘라 둔 그림이 없으면 같은 모양(밝은 둥근 사각 + 검은 글자)으로 그린다."""
    p = GEN / "icons" / f"{name}.png"
    if p.exists():
        im = Image.open(p).convert("RGBA")
        bg = np.asarray(im)[..., :3].astype(int).sum(-1)
        a = np.where(bg < 60, 0, 255).astype(np.uint8)  # 잘라 낸 검은 배경을 투명으로
        im.putalpha(Image.fromarray(a).filter(ImageFilter.GaussianBlur(0.6)))
        return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    label = SYMBOL.get(name, name)
    # 화살표 등 기호는 Black Han Sans 에 없으므로 나눔고딕으로
    f = font(FONT_HEAD if label.isascii() else FONT_BODY, int(h * 0.62))
    tw = f.getbbox(label)[2]
    w = max(h, tw + int(h * 0.5))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 3 if len(label) > 1 else h // 2, fill=(225, 225, 225, 255))
    d.text((w / 2, h / 2), label, font=f, fill=(20, 20, 20, 255), anchor="mm")
    return im


def runs(text):
    """'{R} 스틱을' → [('icon','R'), ('text',' 스틱을')]"""
    out, p = [], 0
    for m in TOKEN.finditer(text):
        if m.start() > p:
            out.append(("text", text[p:m.start()]))
        out.append(("icon", m.group(1)))
        p = m.end()
    if p < len(text):
        out.append(("text", text[p:]))
    return out


def layout(text, f, width, icon_h):
    """글자·아이콘을 width 안에서 줄바꿈. 한글은 어절(공백) 단위, 너무 긴 어절은 글자 단위."""
    items = []
    for kind, val in runs(text):
        if kind == "icon":
            items.append(("icon", val, icon(val, icon_h).width))
        else:
            for word in re.split(r"(\s+)", val):
                if word:
                    items.append(("text", word, f.getlength(word)))
    lines, cur, cw = [], [], 0
    for it in items:
        if it[0] == "text" and it[1].isspace():
            if cur:
                cur.append(it)
                cw += it[2]
            continue
        if cw + it[2] > width and cur:
            while cur and cur[-1][0] == "text" and cur[-1][1].isspace():
                cw -= cur.pop()[2]
            lines.append(cur)
            cur, cw = [], 0
        cur.append(it)
        cw += it[2]
    if cur:
        lines.append(cur)
    return lines


def draw_lines(img, lines, x, y, f, color, line_h, icon_h):
    d = ImageDraw.Draw(img)
    for line in lines:
        cx = x
        for kind, val, w in line:
            if kind == "icon":
                im = icon(val, icon_h)
                img.alpha_composite(im, (int(cx), int(y + (line_h - icon_h) / 2)))
            else:
                d.text((cx, y + line_h / 2), val, font=f, fill=color, anchor="lm")
            cx += w
        y += line_h
    return y


def star(img, x, y, size):
    d = ImageDraw.Draw(img)
    pts = []
    for i in range(10):
        r = size / 2 if i % 2 == 0 else size / 5
        a = -np.pi / 2 + i * np.pi / 5
        pts.append((x + r * np.cos(a), y + r * np.sin(a)))
    d.polygon(pts, fill=WHITE)


def text_page(page, bg):
    img = bg.copy()
    d = ImageDraw.Draw(img)
    hf = font(FONT_HEAD, 22)
    if page.get("header"):
        d.text((RIGHT, 26), page["header"]["ko"], font=hf, fill=GREY, anchor="rm")
    if page.get("number"):
        d.text((RIGHT, 507), page["number"], font=hf, fill=GREY, anchor="rm")
    head_f = font(FONT_HEAD, 32)
    body_f = font(FONT_BODY, 19)
    body_lh, icon_h = 30, 26
    y_cursor = 0
    for b in page["blocks"]:
        y = max(b.get("y", y_cursor) - 18, y_cursor)
        if b["type"] == "heading":
            star(img, 38, y + 21, 22)
            tx = LEFT
            d.text((tx, y + 21), b["ko"], font=head_f, fill=YELLOW, anchor="lm")
            tw = head_f.getlength(b["ko"])
            star(img, tx + tw + 15, y + 21, 22)
            y_cursor = y + 44
        elif b["type"] == "body":
            lines = layout(b["ko"], body_f, RIGHT - LEFT, icon_h)
            y_cursor = draw_lines(img, lines, LEFT, y, body_f, WHITE, body_lh, icon_h) + 6
        elif b["type"] == "list" and b.get("y", 0) >= 470:
            # 하단 버튼 안내줄: 원본처럼 가로 한 줄
            x = LEFT
            for it in b["items"]:
                key, val = (c.strip() for c in it["ko"].split("|", 1))
                line = f"{key} {val}"
                draw_lines(img, layout(line, body_f, 400, icon_h), x, 495, body_f, WHITE, body_lh, icon_h)
                x += sum(w for ln in layout(line, body_f, 400, icon_h) for _, _, w in ln) + 30
        elif b["type"] == "list" and len(b["items"]) > 4 and all("|" in it["ko"] for it in b["items"]):
            # 긴 2칸 표는 2단 격자로(원본 버튼 표 배치)
            half = (RIGHT - LEFT) // 2
            for i, it in enumerate(b["items"]):
                key, val = (c.strip() for c in it["ko"].split("|", 1))
                x = LEFT + 10 + (i % 2) * half
                yy = y + (i // 2) * body_lh
                draw_lines(img, layout(key, body_f, 110, icon_h), x, yy, body_f, WHITE, body_lh, icon_h)
                draw_lines(img, layout(val, body_f, half - 130, icon_h), x + 120, yy, body_f, WHITE, body_lh, icon_h)
            y_cursor = y + ((len(b["items"]) + 1) // 2) * body_lh + 6
        elif b["type"] == "list":
            for it in b["items"]:
                cols = [c.strip() for c in it["ko"].split("|")]
                if len(cols) == 2 and page["kind"] == "toc":
                    d.text((LEFT + 10, y + body_lh / 2), cols[0], font=body_f, fill=WHITE, anchor="lm")
                    d.text((LEFT + 330, y + body_lh / 2), cols[1], font=body_f, fill=WHITE, anchor="rm")
                    y += body_lh
                elif len(cols) == 2:
                    col_w = b.get("col", 200)
                    draw_lines(img, layout(cols[0], body_f, col_w - 10, icon_h), LEFT + 10, y, body_f, WHITE,
                               body_lh, icon_h)
                    lines = layout(cols[1], body_f, RIGHT - LEFT - col_w, icon_h)
                    y = draw_lines(img, lines, LEFT + col_w, y, body_f, WHITE, body_lh, icon_h)
                else:
                    lines = layout(cols[0], body_f, RIGHT - LEFT - 20, icon_h)
                    y = draw_lines(img, lines, LEFT + 20, y, body_f, WHITE, body_lh, icon_h)
            y_cursor = y + 6
    if y_cursor > 490:
        raise ValueError(f"{page['page']}쪽 내용이 넘침 (y={y_cursor})")
    return img


def diagram_page(page, src):
    """그림 쪽: 원본에서 영어 설명 글자만 지우고(주변색으로 메움) 한글 설명을 같은 자리에 쓴다."""
    import cv2
    im = np.asarray(src.convert("RGB"))[:H, :W].copy()
    f = font(FONT_BODY, 19)
    hf = font(FONT_HEAD, 22)
    mask = np.zeros((H, W), np.uint8)
    for lb in page["labels"]:
        x, y = lb["x"], lb["y"]
        w, n_lines = lb["erase"]  # 원본 영어 설명이 차지하던 폭(px)·줄 수
        x0 = {"left": x - 4, "right": x - w, "center": x - w // 2}[lb.get("align", "left")]
        mask[max(0, y - 16):y + 16 + 26 * (n_lines - 1), max(0, x0):min(W, x0 + w)] = 255
    if page.get("header"):
        mask[10:42, 480:950] = 255
    gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    mask = np.where((mask > 0) & (gray > 70), 255, 0).astype(np.uint8)  # 밝은 글자 픽셀만
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    clean = cv2.inpaint(cv2.cvtColor(im, cv2.COLOR_RGB2BGR), mask, 5, cv2.INPAINT_TELEA)
    img = Image.fromarray(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB)).convert("RGBA")
    d = ImageDraw.Draw(img)
    if page.get("header"):
        d.text((RIGHT, 26), page["header"]["ko"], font=hf, fill=GREY, anchor="rm")
    for lb in page["labels"]:
        anchor = {"left": "lm", "right": "rm", "center": "mm"}[lb.get("align", "left")]
        y = lb["y"]
        for line in lb["ko"].split("\n"):
            parts = runs(line)
            if any(k == "icon" for k, _ in parts):
                lines = layout(line, f, 400, 24)
                draw_lines(img, lines, lb["x"], y - 13, f, WHITE, 26, 24)
            else:
                d.text((lb["x"], y), line, font=f, fill=WHITE, anchor=anchor)
            y += 26
    return img


def cover_page(src):
    """표지: 로고 아래 흰 'MANUAL' 글자만 주변 배경으로 메우고 같은 크기의 '설명서'를 쓴다."""
    import cv2
    im = np.asarray(src.convert("RGB"))[:H, :W].copy()
    x0, y0, x1, y1 = 365, 330, 612, 392
    gray = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    mask = np.zeros((H, W), np.uint8)
    mask[y0:y1, x0:x1] = (gray[y0:y1, x0:x1] > 90) * 255
    mask = cv2.dilate(mask, np.ones((7, 7), np.uint8))
    clean = cv2.inpaint(cv2.cvtColor(im, cv2.COLOR_RGB2BGR), mask, 9, cv2.INPAINT_TELEA)
    img = Image.fromarray(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB)).convert("RGBA")
    # 원본처럼 위는 밝고 아래로 어두워지는 흰 글자
    f = font(FONT_HEAD, 58)
    txt = Image.new("L", (W, H), 0)
    ImageDraw.Draw(txt).text(((x0 + x1) / 2, (y0 + y1) / 2), "설명서", font=f, fill=255, anchor="mm")
    grad = Image.linear_gradient("L").resize((W, y1 - y0 + 10)).point(lambda v: 245 - v * 70 // 255)
    shade = Image.new("L", (W, H), 0)
    shade.paste(grad, (0, y0 - 5))
    white = Image.merge("RGBA", (shade, shade, shade, txt))
    img.alpha_composite(white)
    return img


def cover_or_toc(page, src, bg):
    if page["kind"] == "cover":
        return src.convert("RGBA").crop((0, 0, W, H))  # 표지는 로고 그림이라 원본 유지(제목 아래 MANUAL 만 교체)
    return text_page(page, bg)


def render(page, src, bg):
    if page["kind"] == "diagram":
        img = diagram_page(page, src)
    elif page["kind"] in ("cover", "toc"):
        img = cover_or_toc(page, src, bg)
        if page["kind"] == "cover":
            img = cover_page(src)
    else:
        img = text_page(page, bg)
    full = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
    full.alpha_composite(img.convert("RGBA"), (0, 0))
    return full


def render_all(want=None):
    """원본 재료가 없으면 manual_assets 로 만든 뒤 쪽을 그린다."""
    if not (GEN / "background.png").exists():
        import manual_assets
        manual_assets.prepare()
    pages = json.loads((ASSET / "manual.json").read_text(encoding="utf-8"))
    bg = Image.open(GEN / "background.png").convert("RGBA")
    out = GEN / "pages"
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for page in pages:
        n = page["page"]
        if want is not None and n not in want:
            continue
        img = render(page, Image.open(str(SRC).format(n)), bg)
        img.convert("RGB").save(out / f"ko_{n}.png")
        done.append(out / f"ko_{n}.png")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages")
    args = ap.parse_args()
    want = {int(p) for p in args.pages.split(",")} if args.pages else None
    for p in render_all(want):
        print(p)


if __name__ == "__main__":
    main()
