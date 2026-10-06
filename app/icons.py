"""간단한 벡터 아이콘. 512px 캔버스에 그린 뒤 원하는 크기로 줄여 쓴다."""
from functools import lru_cache

from PIL import Image, ImageDraw

S = 512


def _canvas():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _check(d, c, w=44, box=(150, 260, 230, 340, 370, 180)):
    x1, y1, x2, y2, x3, y3 = box
    d.line([(x1, y1), (x2, y2), (x3, y3)], fill=c, width=w, joint="curve")
    for x, y in [(x1, y1), (x3, y3)]:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=c)


def _qmark(d, c, font):
    d.text((S / 2, S / 2 + 10), "?", font=font, fill=c, anchor="mm")


def draw_icon(name: str, color: str, fg: str = "#ffffff", font=None) -> Image.Image:
    """원형 배지 형태 아이콘(question, warning 등) 또는 단색 아이콘."""
    im, d = _canvas()
    if name == "question":
        d.ellipse([16, 16, S - 16, S - 16], fill=color)
        _qmark(d, fg, font)
    elif name == "check":
        d.ellipse([16, 16, S - 16, S - 16], fill=color)
        _check(d, fg)
    elif name == "x_mark":
        d.ellipse([16, 16, S - 16, S - 16], fill=color)
        d.line([(170, 170), (342, 342)], fill=fg, width=50)
        d.line([(342, 170), (170, 342)], fill=fg, width=50)
    elif name == "info":
        d.ellipse([16, 16, S - 16, S - 16], fill=color)
        d.ellipse([226, 120, 286, 180], fill=fg)
        d.rounded_rectangle([228, 215, 284, 392], 24, fill=fg)
    elif name == "warning":
        d.polygon([(256, 40), (488, 450), (24, 450)], fill=color)
        d.rounded_rectangle([230, 170, 282, 330], 22, fill=fg)
        d.ellipse([228, 360, 284, 416], fill=fg)
    elif name == "search":
        d.ellipse([60, 60, 340, 340], outline=color, width=52)
        d.line([(300, 300), (452, 452)], fill=color, width=64)
        d.ellipse([420, 420, 484, 484], fill=color)
    elif name == "thermometer":
        d.rounded_rectangle([196, 40, 316, 340], 60, fill=color)
        d.ellipse([146, 290, 366, 500], fill=color)
        d.rounded_rectangle([232, 120, 280, 360], 24, fill=fg)
        d.ellipse([196, 340, 316, 460], fill=fg)
        for y in (110, 170, 230):
            d.line([(330, y), (390, y)], fill=color, width=22)
    elif name in ("shield", "shield_crack"):
        d.polygon([(256, 30), (450, 100), (430, 300), (256, 490), (82, 300), (62, 100)], fill=color)
        if name == "shield_crack":
            d.line([(256, 60), (220, 190), (300, 260), (230, 350), (262, 470)], fill=fg, width=30, joint="curve")
        else:
            _check(d, fg, 40, (160, 260, 230, 330, 360, 190))
    elif name == "hospital":
        d.rounded_rectangle([90, 110, 422, 470], 30, fill=color)
        d.rounded_rectangle([196, 50, 316, 130], 20, fill=color)
        d.rectangle([230, 190, 282, 390], fill=fg)
        d.rectangle([156, 264, 356, 316], fill=fg)
    elif name == "pharmacy":
        cap = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cap)
        cd.rounded_rectangle([60, 176, 452, 336], 80, fill=color)
        cd.rectangle([256, 196, 432, 316], fill=fg)
        cd.rounded_rectangle([256, 196, 432, 316], 60, fill=fg)
        cd.rounded_rectangle([60, 176, 452, 336], 80, outline=color, width=26)
        im = cap.rotate(40, resample=Image.BICUBIC)
    elif name == "money":
        d.rounded_rectangle([40, 120, 472, 392], 40, fill=color)
        d.ellipse([186, 186, 326, 326], outline=fg, width=26)
        d.text((256, 258), "₩", font=font.font_variant(size=110) if font else None, fill=fg, anchor="mm")
    elif name == "calendar":
        d.rounded_rectangle([60, 90, 452, 460], 40, fill=color)
        d.rectangle([60, 200, 452, 220], fill=fg)
        for x in (150, 362):
            d.rounded_rectangle([x - 18, 50, x + 18, 140], 18, fill=color)
        for i in range(3):
            for j in range(2):
                d.rounded_rectangle([110 + i * 110, 260 + j * 90, 180 + i * 110, 320 + j * 90], 10, fill=fg)
    elif name == "people":
        for cx, r, y0 in [(170, 70, 90), (342, 70, 90)]:
            d.ellipse([cx - r, y0, cx + r, y0 + 2 * r], fill=color)
            d.pieslice([cx - 120, 250, cx + 120, 490], 180, 360, fill=color)
            d.rectangle([cx - 120, 368, cx + 120, 440], fill=color)
    elif name == "phone":
        d.rounded_rectangle([150, 40, 362, 472], 40, fill=color)
        d.rounded_rectangle([176, 100, 336, 380], 10, fill=fg)
        d.ellipse([236, 400, 276, 440], fill=fg)
    elif name == "megaphone":
        d.polygon([(90, 200), (330, 80), (330, 430), (90, 310)], fill=color)
        d.rounded_rectangle([50, 190, 130, 320], 20, fill=color)
        d.polygon([(130, 310), (200, 310), (230, 450), (170, 450)], fill=color)
        for a in (-1, 0, 1):
            d.line([(380, 255 + a * 90), (450, 255 + a * 130)], fill=color, width=26)
    elif name == "home":
        d.polygon([(256, 50), (480, 250), (32, 250)], fill=color)
        d.rectangle([100, 240, 412, 470], fill=color)
        d.rounded_rectangle([216, 330, 296, 470], 12, fill=fg)
    elif name == "document":
        d.polygon([(100, 40), (340, 40), (420, 120), (420, 472), (100, 472)], fill=color)
        for y in (180, 260, 340):
            d.rounded_rectangle([160, y, 360, y + 30], 14, fill=fg)
    elif name == "heart":
        d.ellipse([50, 80, 270, 300], fill=color)
        d.ellipse([242, 80, 462, 300], fill=color)
        d.polygon([(62, 236), (450, 236), (256, 460)], fill=color)
    elif name == "leaf":
        d.chord([60, 60, 452, 452], 180, 360, fill=color)
        d.chord([60, -136, 452, 452], 0, 90, fill=color)
        d.ellipse([60, 60, 452, 452], fill=color)
        d.line([(120, 400), (360, 160)], fill=fg, width=26)
    elif name == "car":
        d.rounded_rectangle([40, 230, 472, 390], 50, fill=color)
        d.polygon([(120, 240), (170, 120), (342, 120), (392, 240)], fill=color)
        d.polygon([(190, 230), (215, 160), (297, 160), (322, 230)], fill=fg)
        for cx in (140, 372):
            d.ellipse([cx - 56, 340, cx + 56, 452], fill=color)
            d.ellipse([cx - 24, 372, cx + 24, 420], fill=fg)
    elif name == "chart":
        for i, h in enumerate((160, 260, 360)):
            d.rounded_rectangle([80 + i * 130, 450 - h, 170 + i * 130, 450], 16, fill=color)
        d.rectangle([50, 450, 462, 476], fill=color)
    else:
        d.ellipse([16, 16, S - 16, S - 16], fill=color)
    return im


@lru_cache(maxsize=256)
def icon_image(name: str, size: int, color: str, fg: str, font_path: str) -> Image.Image:
    from PIL import ImageFont
    font = ImageFont.truetype(font_path, 330)
    return draw_icon(name, color, fg, font).resize((size, size), Image.LANCZOS)
