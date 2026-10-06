"""장면 → 1080x1920 프레임 이미지 (Pillow)."""
import math
import os
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .icons import icon_image

W, H = 1080, 1920
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")

INK, SUB, ACC, TEAL, RED = "#161e2e", "#5a6070", "#e25822", "#0e7490", "#d6393a"
TRACK, CARD, SUB_BG = "#e4ddd0", "#ffffff", "#232b3b"
ICON_COLOR = {"question": RED, "x_mark": RED, "warning": ACC, "shield_crack": RED, "thermometer": ACC,
              "heart": RED, "megaphone": ACC}

ANIM_END = 1.6  # 장면 시작 후 이 시간 이후로는 정지 화면


def font_path(weight: str) -> str:
    return os.path.join(FONT_DIR, f"Pretendard-{weight}.otf")


@lru_cache(maxsize=64)
def F(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(weight), size)


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_back(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


# ------------------------------------------------------------------ 텍스트 도구

def parse_marked(line: str):
    """'인터넷 **비만치료제**' → [(text, accent?)]"""
    parts = re.split(r"(\*\*[^*]+\*\*)", line)
    return [(p[2:-2], True) if p.startswith("**") else (p, False) for p in parts if p]


def wrap_text(text: str, font, max_w: int) -> list:
    """단어 단위 줄바꿈 (한 단어가 너무 길면 글자 단위)."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = f"{cur} {word}".strip()
            if font.getlength(cand.replace("**", "")) <= max_w:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = word
            while font.getlength(cur.replace("**", "")) > max_w and len(cur) > 1:
                k = len(cur)
                while k > 1 and font.getlength(cur[:k].replace("**", "")) > max_w:
                    k -= 1
                lines.append(cur[:k])
                cur = cur[k:]
        lines.append(cur)
    # 줄을 넘어간 강조 표시(**)를 줄마다 닫고 다시 연다
    fixed, open_ = [], False
    for ln in lines:
        if open_:
            ln = "**" + ln
        open_ = ln.count("**") % 2 == 1
        fixed.append(ln + ("**" if open_ else ""))
    return fixed


def draw_rich(d: ImageDraw.ImageDraw, lines: list, font, cx: int, y: int, lh: int, color=INK, accent=ACC):
    for ln in lines:
        segs = parse_marked(ln)
        total = sum(font.getlength(t) for t, _ in segs)
        x = cx - total / 2
        for t, acc in segs:
            d.text((x, y), t, font=font, fill=accent if acc else color, anchor="ls")
            x += font.getlength(t)
        y += lh
    return y


def balanced_split(text: str, font, max_w: int) -> list:
    """자막용: 두 줄이면 길이를 비슷하게 나눈다."""
    if font.getlength(text) <= max_w:
        return [text]
    words = text.split(" ")
    best, best_diff = None, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        la, lb = font.getlength(a), font.getlength(b)
        if la <= max_w and lb <= max_w and abs(la - lb) < best_diff:
            best, best_diff = [a, b], abs(la - lb)
    return best or wrap_text(text, font, max_w)


# ------------------------------------------------------------------ 레이어

def new_layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def blend(base: Image.Image, layer: Image.Image, alpha: float = 1.0, dy: int = 0, scale: float = 1.0, center=None):
    if alpha <= 0:
        return
    if scale != 1.0 and center:
        bbox = layer.getbbox()
        if not bbox:
            return
        crop = layer.crop(bbox)
        nw, nh = max(1, int(crop.width * scale)), max(1, int(crop.height * scale))
        crop = crop.resize((nw, nh), Image.BICUBIC)
        layer = new_layer()
        cx, cy = center
        layer.paste(crop, (int(cx - nw / 2), int(cy - nh / 2)))
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    if dy:
        moved = new_layer()
        moved.paste(layer, (0, dy))
        layer = moved
    base.alpha_composite(layer)


def paste_icon(img, name, size, cx, cy, color=None):
    color = color or ICON_COLOR.get(name, TEAL)
    ic = icon_image(name, size, color, "#ffffff", font_path("ExtraBold"))
    img.alpha_composite(ic, (int(cx - size / 2), int(cy - size / 2)))


# ------------------------------------------------------------------ 공통 화면

def background(meta: dict) -> Image.Image:
    img = Image.new("RGBA", (W, H), "#f7f4ee")
    grad = Image.linear_gradient("L").resize((W, H))
    bottom = Image.new("RGBA", (W, H), "#f0e9de")
    img = Image.composite(bottom, img, grad)
    d = ImageDraw.Draw(img)
    d.ellipse([1000 - 260, 80 - 260, 1000 + 260, 80 + 260], fill="#f5e2d4")
    d.ellipse([40 - 300, 1600 - 300, 40 + 300, 1600 + 300], fill="#e3e5dd")
    agency = meta.get("agency") or "정부"
    date = meta.get("release_date") or ""
    pill = f"{agency} 보도자료" + (f"  ·  {date}" if date else "")
    f = F("SemiBold", 30)
    tw = f.getlength(pill)
    d.rounded_rectangle([60, 140, 60 + tw + 56, 204], 32, fill=INK)
    d.text((88, 173), pill, font=f, fill="#ffffff", anchor="lm")
    src = f"출처: {agency} 보도자료" + (f"({date})" if date else "")
    d.text((W / 2, 1832), src, font=F("Regular", 28), fill="#7a7f8a", anchor="mm")
    return img


def draw_progress(img, frac: float):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 82, 1020, 94], 6, fill=TRACK)
    x = 60 + max(0.0, min(1.0, frac)) * 960
    if x > 66:
        d.rounded_rectangle([60, 82, x, 94], 6, fill=ACC)


@lru_cache(maxsize=128)
def subtitle_layer(text: str) -> Image.Image:
    layer = new_layer()
    if not text:
        return layer
    d = ImageDraw.Draw(layer)
    f = F("Bold", 46)
    lines = balanced_split(text, f, 860)[:3]
    lh = 66
    bh = lh * len(lines) + 64
    cy = 1585
    top = cy - bh / 2
    d.rounded_rectangle([70, top, 1010, top + bh], 28, fill=SUB_BG)
    y = top + 32 + lh / 2
    for ln in lines:
        d.text((W / 2, y), ln, font=f, fill="#ffffff", anchor="mm")
        y += lh
    return layer


# ------------------------------------------------------------------ 템플릿

def _headline(d, text, size=56, y=500, weight="Bold", max_w=920, lh_ratio=1.28):
    f = F(weight, size)
    lines = wrap_text(text, f, max_w)
    return draw_rich(d, lines, f, W // 2, y, int(size * lh_ratio))


def t_hook(img, s, t):
    icon = s.get("icon") or "question"
    lay = new_layer()
    paste_icon(lay, icon, 170, W // 2, 470)
    k = ease_back(t / 0.5)
    blend(img, lay, alpha=min(1, t / 0.2), scale=max(0.01, k), center=(W // 2, 470))
    lay = new_layer()
    d = ImageDraw.Draw(lay)
    _headline(d, s.get("headline", ""), size=100, y=720, weight="ExtraBold", max_w=940, lh_ratio=1.24)
    blend(img, lay, alpha=ease((t - 0.15) / 0.4), dy=int(40 * (1 - ease((t - 0.15) / 0.4))))


def _fmt_num(v: float, decimals: int) -> str:
    return f"{v:,.{decimals}f}"


def t_counter(img, s, t):
    d = ImageDraw.Draw(img)
    _headline(d, s.get("headline", ""), size=56, y=500)
    raw = str(s.get("value", 0)).replace(",", "")
    try:
        target = float(raw)
    except ValueError:
        target = 0.0
    dec = len(raw.split(".")[1]) if "." in raw else 0
    cur = target * ease(t / 1.1)
    num = _fmt_num(cur, dec)
    size = 300
    fn = F("ExtraBold", size)
    unit = s.get("unit", "")
    fu = F("ExtraBold", 96)
    full_w = fn.getlength(_fmt_num(target, dec)) + (fu.getlength(unit) + 24 if unit else 0)
    while full_w > 960 and size > 120:
        size -= 20
        fn = F("ExtraBold", size)
        full_w = fn.getlength(_fmt_num(target, dec)) + (fu.getlength(unit) + 24 if unit else 0)
    x0 = W / 2 - full_w / 2
    base_y = 960
    d.text((x0 + fn.getlength(_fmt_num(target, dec)), base_y), num, font=fn, fill=ACC, anchor="rs")
    if unit:
        d.text((x0 + fn.getlength(_fmt_num(target, dec)) + 24, base_y - 10), unit, font=fu, fill=ACC, anchor="ls")
    lw = 600 * ease((t - 0.2) / 0.9)
    if lw > 12:
        d.rounded_rectangle([W / 2 - lw / 2, 1030, W / 2 + lw / 2, 1042], 6, fill=ACC)
    if s.get("subline"):
        f = F("Regular", 44)
        for i, ln in enumerate(wrap_text(s["subline"], f, 900)[:2]):
            d.text((W / 2, 1140 + i * 60), ln, font=f, fill=SUB, anchor="ms")


def t_bar(img, s, t):
    d = ImageDraw.Draw(img)
    _headline(d, s.get("headline", ""), size=56, y=470)
    items = (s.get("items") or [])[:5]
    if not items:
        return
    vals = [float(i.get("value") or 0) for i in items]
    unit = s.get("unit", "%")
    vmax = max(vals) or 1
    full = 100.0 if unit == "%" and vmax <= 100 else vmax
    top = 600
    gap = 160 if len(items) <= 4 else 140
    for k, (it, v) in enumerate(zip(items, vals)):
        y = top + k * gap
        p = ease((t - 0.15 - k * 0.12) / 0.9)
        d.text((90, y + 44), str(it.get("label", "")), font=F("Bold", 44), fill=INK, anchor="ls")
        color = ACC if v == vmax else TEAL
        d.rounded_rectangle([90, y + 66, 840, y + 110], 22, fill=TRACK)
        bw = max(44, 750 * (v / full) * p)
        d.rounded_rectangle([90, y + 66, 90 + bw, y + 110], 22, fill=color)
        txt = f"{v * p:.{1 if v != int(v) else 0}f}{unit}"
        d.text((870, y + 106), txt, font=F("ExtraBold", 50), fill=color, anchor="ls")


def t_reasons(img, s, t):
    d = ImageDraw.Draw(img)
    _headline(d, s.get("headline", ""), size=60, y=470)
    items = (s.get("items") or [])[:4]
    top = 590
    for k, it in enumerate(items):
        p = ease((t - 0.2 - k * 0.25) / 0.45)
        if p <= 0:
            continue
        lay = new_layer()
        ld = ImageDraw.Draw(lay)
        y = top + k * 200
        ld.rounded_rectangle([70, y, 1010, y + 170], 28, fill=CARD)
        paste_icon(lay, it.get("icon") or "check", 100, 160, y + 85)
        f = F("Bold", 48)
        lines = wrap_text(str(it.get("text", "")), f, 700)[:2]
        ly = y + 85 - (len(lines) - 1) * 31
        for ln in lines:
            ld.text((250, ly), ln, font=f, fill=INK, anchor="lm")
            ly += 62
        blend(img, lay, alpha=p, dy=int(30 * (1 - p)))


def t_icon_message(img, s, t):
    icon = s.get("icon") or "info"
    lay = new_layer()
    paste_icon(lay, icon, 220, W // 2, 520)
    blend(img, lay, alpha=min(1, t / 0.2), scale=max(0.01, ease_back(t / 0.5)), center=(W // 2, 520))
    lay = new_layer()
    d = ImageDraw.Draw(lay)
    y = _headline(d, s.get("headline", ""), size=84, y=770, weight="ExtraBold", max_w=940, lh_ratio=1.26)
    if s.get("subline"):
        f = F("Regular", 44)
        for i, ln in enumerate(wrap_text(s["subline"], f, 900)[:2]):
            d.text((W / 2, y + 40 + i * 60), ln, font=f, fill=SUB, anchor="ms")
    p = ease((t - 0.15) / 0.4)
    blend(img, lay, alpha=p, dy=int(40 * (1 - p)))


def t_flow(img, s, t):
    d = ImageDraw.Draw(img)
    _headline(d, s.get("headline", ""), size=64, y=470, weight="ExtraBold")
    steps = (s.get("steps") or [])[:4]
    n = len(steps)
    if not n:
        return
    r = 115 if n <= 3 else 92
    span = min(W - 2 * (r + 50), 640 if n == 2 else 900)
    xs = [W / 2 - span / 2 + span * i / (n - 1) for i in range(n)] if n > 1 else [W / 2]
    cy = 790
    for k, (st, x) in enumerate(zip(steps, xs)):
        p = ease((t - 0.2 - k * 0.3) / 0.45)
        if p <= 0:
            continue
        lay = new_layer()
        ld = ImageDraw.Draw(lay)
        if k > 0:
            ax0, ax1 = xs[k - 1] + r + 14, x - r - 14
            ld.line([(ax0, cy), (ax1, cy)], fill="#59606e", width=10)
            ld.line([(ax1 - 22, cy - 18), (ax1, cy), (ax1 - 22, cy + 18)], fill="#59606e", width=10, joint="curve")
        ld.ellipse([x - r, cy - r, x + r, cy + r], fill=CARD)
        paste_icon(lay, st.get("icon") or "check", int(r * 1.0), x, cy)
        f = F("Bold", 44 if n <= 3 else 38)
        for i, ln in enumerate(wrap_text(str(st.get("label", "")), f, 2 * r + 40)[:3]):
            ld.text((x, cy + r + 80 + i * 58), ln, font=f, fill=INK, anchor="ms")
        blend(img, lay, alpha=p, dy=int(24 * (1 - p)))


def t_cta(img, s, t):
    lay = new_layer()
    paste_icon(lay, s.get("icon") or "search", 180, W // 2, 480)
    blend(img, lay, alpha=min(1, t / 0.2), scale=max(0.01, ease_back(t / 0.5)), center=(W // 2, 480))
    lay = new_layer()
    d = ImageDraw.Draw(lay)
    y = _headline(d, s.get("headline", ""), size=80, y=690, weight="ExtraBold", lh_ratio=1.25)
    box = s.get("url") or s.get("phone")
    if box:
        f = F("ExtraBold", 54)
        while f.getlength(box) > 860 and f.size > 30:
            f = F("ExtraBold", f.size - 4)
        bw = f.getlength(box) + 100
        by = y + 20
        d.rounded_rectangle([W / 2 - bw / 2, by, W / 2 + bw / 2, by + 120], 60, fill=CARD, outline=TEAL, width=6)
        d.text((W / 2, by + 60), box, font=f, fill=TEAL, anchor="mm")
        y = by + 120 + 30
    if s.get("subline"):
        f = F("Regular", 44)
        for i, ln in enumerate(wrap_text(s["subline"], f, 900)[:2]):
            d.text((W / 2, y + 60 + i * 60), ln, font=f, fill=SUB, anchor="ms")
    p = ease((t - 0.15) / 0.4)
    blend(img, lay, alpha=p, dy=int(40 * (1 - p)))


TEMPLATE_FN = {"hook": t_hook, "counter": t_counter, "bar": t_bar, "reasons": t_reasons,
               "icon_message": t_icon_message, "flow": t_flow, "cta": t_cta}


def content_layer(scene: dict, t: float) -> Image.Image:
    lay = new_layer()
    fn = TEMPLATE_FN.get(scene.get("template"), t_icon_message)
    fn(lay, scene, t)
    return lay


class SceneRenderer:
    """프레임 렌더러. 장면별 정지 레이어를 캐시해 속도를 낸다."""

    def __init__(self, meta: dict):
        self.bg = background(meta)
        self._static = {}

    def frame(self, scene_idx: int, scene: dict, t: float, progress: float, subtitle: str) -> Image.Image:
        img = self.bg.copy()
        draw_progress(img, progress)
        if t >= ANIM_END:
            if scene_idx not in self._static:
                self._static[scene_idx] = content_layer(scene, ANIM_END + 10)
            img.alpha_composite(self._static[scene_idx])
        else:
            lay = content_layer(scene, t)
            p = ease(t / 0.35)
            blend(img, lay, alpha=p, dy=int(30 * (1 - p)))
        img.alpha_composite(subtitle_layer(subtitle))
        return img

    def still(self, scene: dict, progress: float, subtitle: str) -> Image.Image:
        img = self.bg.copy()
        draw_progress(img, progress)
        img.alpha_composite(content_layer(scene, ANIM_END + 10))
        img.alpha_composite(subtitle_layer(subtitle))
        return img
