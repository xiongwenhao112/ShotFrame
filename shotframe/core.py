# -*- coding: utf-8 -*-
"""核心加框引擎：把截图包装成清晰可辨的「截图卡片」。

两个正交维度：
- 窗口框 frame：mac / mac-dark / win11 / browser / plain
- 背景 backdrop：纯色若干 + 渐变若干

内容 100% 原样保留，只加外包装。
"""
import io
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 样式定义

FRAMES = {
    "mac":      {"name": "Mac 浅色"},
    "mac-dark": {"name": "Mac 深色"},
    "win11":    {"name": "Windows 风"},
    "browser":  {"name": "浏览器"},
    "plain":    {"name": "极简卡片"},
}

BACKDROPS = {
    "gray":        {"name": "浅灰", "type": "solid", "colors": [(241, 242, 246)]},
    "purple":      {"name": "浅紫", "type": "solid", "colors": [(240, 238, 248)]},
    "blue":        {"name": "浅蓝", "type": "solid", "colors": [(235, 242, 250)]},
    "green":       {"name": "浅绿", "type": "solid", "colors": [(237, 245, 239)]},
    "white":       {"name": "纯白", "type": "solid", "colors": [(255, 255, 255)]},
    "dark":        {"name": "深空", "type": "solid", "colors": [(38, 40, 46)]},
    "grad-violet": {"name": "紫粉渐变", "type": "gradient",
                    "colors": [(139, 92, 246), (236, 72, 153)]},
    "grad-ocean":  {"name": "蓝青渐变", "type": "gradient",
                    "colors": [(59, 130, 246), (34, 211, 238)]},
    "grad-sunset": {"name": "落日渐变", "type": "gradient",
                    "colors": [(251, 146, 60), (236, 72, 153)]},
    "grad-forest": {"name": "青碧渐变", "type": "gradient",
                    "colors": [(16, 185, 129), (59, 130, 246)]},
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# 旧版 preset 参数兼容（v0.1 只有底色一种维度）
LEGACY_PRESETS = {"gray", "purple", "blue", "green"}


@dataclass
class FrameStyle:
    frame: str = "mac"           # FRAMES key
    backdrop: str = "gray"       # BACKDROPS key
    label: str = "实测截图"       # 标题栏文字 / 浏览器地址栏文字，可为空
    show_dots: bool = True       # mac/browser 的三个圆点
    min_width: int = 200         # 小于该尺寸跳过（表情/图标）
    min_height: int = 100


# ---------------------------------------------------------------- 字体

_FONT_CANDIDATES = [
    "msyh.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc",              # Windows
    "/System/Library/Fonts/PingFang.ttc",                             # macOS
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",         # Linux
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


def load_font(size):
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- 工具

def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def _lerp(c1, c2, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def build_backdrop(size, backdrop_key):
    """生成背景画布（纯色或对角渐变）。"""
    spec = BACKDROPS.get(backdrop_key, BACKDROPS["gray"])
    w, h = size
    if spec["type"] == "solid":
        return Image.new("RGBA", size, tuple(spec["colors"][0]) + (255,))
    c1, c2 = spec["colors"]
    n = 64
    small = Image.new("RGB", (n, n))
    px = small.load()
    for y in range(n):
        for x in range(n):
            px[x, y] = _lerp(c1, c2, (x + y) / (2 * (n - 1)))
    return small.resize((w, h), Image.BILINEAR).convert("RGBA")


def _is_dark_backdrop(backdrop_key):
    spec = BACKDROPS.get(backdrop_key, BACKDROPS["gray"])
    c = spec["colors"][0]
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) < 100


# ---------------------------------------------------------------- 窗口栏绘制

def _draw_dots(wd, s, cy, style, start_x):
    """画 mac 三圆点，返回下一个元素的 x 起点。"""
    dot_r = round(5.5 * s)
    cx = start_x
    if style.show_dots:
        for color in ((255, 95, 87, 255), (254, 188, 46, 255), (40, 200, 64, 255)):
            wd.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)
            cx += round(20 * s)
        return cx + round(4 * s)
    return start_x - round(6 * s)


def _bar_mac(win, w, bar_h, s, style, dark=False):
    wd = ImageDraw.Draw(win)
    if dark:
        bar, hairline, label_c = (42, 44, 50, 255), (58, 60, 68, 255), (139, 146, 160, 255)
    else:
        bar, hairline, label_c = (247, 248, 250, 255), (233, 234, 239, 255), (152, 160, 174, 255)
    wd.rectangle([0, 0, w - 1, bar_h - 1], fill=bar)
    wd.rectangle([0, bar_h - 1, w - 1, bar_h - 1], fill=hairline)
    cy = bar_h // 2
    next_x = _draw_dots(wd, s, cy, style, round(20 * s))
    if style.label:
        wd.text((next_x + round(6 * s), cy), style.label,
                font=load_font(round(15 * s)), fill=label_c, anchor="lm")


def _bar_win11(win, w, bar_h, s, style):
    wd = ImageDraw.Draw(win)
    bar, hairline = (243, 243, 244, 255), (229, 230, 235, 255)
    glyph = (95, 99, 104, 255)
    wd.rectangle([0, 0, w - 1, bar_h - 1], fill=bar)
    wd.rectangle([0, bar_h - 1, w - 1, bar_h - 1], fill=hairline)
    cy = bar_h // 2
    # 左侧小应用图标 + 标题
    ic = round(8 * s)
    ix = round(16 * s)
    wd.rounded_rectangle([ix, cy - ic, ix + 2 * ic, cy + ic],
                         radius=round(3 * s), fill=(108, 92, 231, 255))
    if style.label:
        wd.text((ix + 2 * ic + round(10 * s), cy), style.label,
                font=load_font(round(14 * s)), fill=(90, 95, 106, 255), anchor="lm")
    # 右侧 最小化/最大化/关闭
    lw = max(1, round(1.4 * s))
    g = round(5.5 * s)
    cx = w - round(24 * s)
    wd.line([cx - g, cy + g, cx + g, cy - g], fill=glyph, width=lw)   # ✕
    wd.line([cx - g, cy - g, cx + g, cy + g], fill=glyph, width=lw)
    cx -= round(34 * s)
    wd.rectangle([cx - g, cy - g, cx + g, cy + g], outline=glyph, width=lw)  # ▢
    cx -= round(34 * s)
    wd.line([cx - g, cy, cx + g, cy], fill=glyph, width=lw)           # ─


def _bar_browser(win, w, bar_h, s, style):
    wd = ImageDraw.Draw(win)
    bar, hairline = (241, 243, 244, 255), (226, 228, 233, 255)
    wd.rectangle([0, 0, w - 1, bar_h - 1], fill=bar)
    wd.rectangle([0, bar_h - 1, w - 1, bar_h - 1], fill=hairline)
    cy = bar_h // 2
    next_x = _draw_dots(wd, s, cy, style, round(20 * s))
    # 地址栏胶囊
    pill_x0 = next_x + round(8 * s)
    pill_x1 = w - round(20 * s)
    ph = round(13 * s)
    if pill_x1 - pill_x0 > round(80 * s):
        wd.rounded_rectangle([pill_x0, cy - ph, pill_x1, cy + ph],
                             radius=ph, fill=(255, 255, 255, 255),
                             outline=(223, 225, 230, 255), width=max(1, round(s)))
        # 小锁
        lk = round(4.5 * s)
        lx = pill_x0 + round(14 * s)
        wd.rounded_rectangle([lx - lk, cy - lk * 0.2, lx + lk, cy + lk + 1],
                             radius=round(1.5 * s), fill=(120, 126, 138, 255))
        wd.arc([lx - lk * 0.7, cy - lk - 1, lx + lk * 0.7, cy + lk * 0.4],
               180, 360, fill=(120, 126, 138, 255), width=max(1, round(1.2 * s)))
        text = style.label if style.label else "example.com"
        wd.text((lx + lk + round(8 * s), cy), text,
                font=load_font(round(13 * s)), fill=(95, 99, 104, 255), anchor="lm")


# ---------------------------------------------------------------- 主渲染

def frame_image(im, style=None):
    """给一张 PIL Image 加框，返回新的 RGB Image。"""
    style = style or FrameStyle()
    im = im.convert("RGB")
    w, h = im.size

    spec = BACKDROPS.get(style.backdrop, BACKDROPS["gray"])
    is_grad = spec["type"] == "gradient"
    dark_bd = _is_dark_backdrop(style.backdrop)

    s = max(0.8, min(1.4, w / 1000.0))
    pad = 1.7 if is_grad else 1.0            # 渐变背景留白更大更透气
    mx = round(26 * s * pad)
    myt = round(20 * s * pad)
    myb = round(34 * s * pad)
    radius = round(12 * s)
    blur = round((16 if is_grad or dark_bd else 12) * s)
    shadow_alpha = 80 if (is_grad or dark_bd) else 60

    if style.frame == "plain":
        bar_h = 0
    elif style.frame == "browser":
        bar_h = round(46 * s)
    else:
        bar_h = round(38 * s)

    win_w, win_h = w, bar_h + h
    cw, ch = win_w + 2 * mx, win_h + myt + myb

    base = build_backdrop((cw, ch), style.backdrop)

    # 投影
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    off = round(5 * s)
    sd.rounded_rectangle(
        [mx, myt + off, mx + win_w - 1, myt + win_h - 1 + off],
        radius=radius, fill=(10, 14, 26, shadow_alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    base = Image.alpha_composite(base, sh)

    # 窗口本体
    win = Image.new("RGBA", (win_w, win_h), (255, 255, 255, 255))
    if style.frame == "mac":
        _bar_mac(win, win_w, bar_h, s, style, dark=False)
    elif style.frame == "mac-dark":
        _bar_mac(win, win_w, bar_h, s, style, dark=True)
    elif style.frame == "win11":
        _bar_win11(win, win_w, bar_h, s, style)
    elif style.frame == "browser":
        _bar_browser(win, win_w, bar_h, s, style)
    win.paste(im, (0, bar_h))

    base.paste(win, (mx, myt), _rounded_mask((win_w, win_h), radius))

    # 描边
    if style.frame == "mac-dark":
        border = (30, 32, 38, 255)
    elif dark_bd:
        border = (70, 74, 84, 255)
    else:
        border = (214, 216, 224, 255)
    bd = ImageDraw.Draw(base)
    bd.rounded_rectangle(
        [mx, myt, mx + win_w - 1, myt + win_h - 1],
        radius=radius, outline=border, width=max(1, round(s)))
    return base.convert("RGB")


# ---------------------------------------------------------------- 文件处理

def process_image_file(path, out_dir=None, style=None):
    """处理单张图片文件，返回输出路径；尺寸过小返回 None。"""
    style = style or FrameStyle()
    im = Image.open(path)
    if im.width < style.min_width or im.height < style.min_height:
        return None
    out = frame_image(im, style)
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "加框")
    os.makedirs(out_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    ext = ext.lower()
    if ext in (".jpg", ".jpeg"):
        dst = os.path.join(out_dir, base + ext)
        out.save(dst, "JPEG", quality=92)
    else:
        dst = os.path.join(out_dir, base + ".png")
        out.save(dst, "PNG", optimize=True)
    return dst


def frame_bytes(data, fmt_hint, style=None):
    """处理内存图片字节，返回 (新字节, 宽, 高)；跳过返回 None。"""
    style = style or FrameStyle()
    im = Image.open(io.BytesIO(data))
    if im.width < style.min_width or im.height < style.min_height:
        return None
    out = frame_image(im, style)
    buf = io.BytesIO()
    if fmt_hint in ("jpg", "jpeg"):
        out.save(buf, "JPEG", quality=92)
    else:
        out.save(buf, "PNG", optimize=True)
    return buf.getvalue(), out.width, out.height


# ---------------------------------------------------------------- 预览样图

def make_sample(width=760, height=470):
    """生成一张演示用的假界面截图，用于实时预览。"""
    im = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(im)
    f_title = load_font(26)
    f_body = load_font(16)
    # 左侧栏
    d.rectangle([0, 0, 168, height], fill=(246, 247, 250))
    d.rounded_rectangle([16, 22, 152, 54], radius=8, fill=(108, 92, 231))
    d.text((26, 38), "ShotFrame", font=f_body, fill=(255, 255, 255), anchor="lm")
    for i in range(5):
        y = 84 + i * 44
        d.rounded_rectangle([16, y, 152, y + 28], radius=6,
                            fill=(235, 236, 242) if i == 1 else (255, 255, 255))
        d.rounded_rectangle([28, y + 10, 120, y + 18], radius=4, fill=(203, 208, 220))
    # 正文
    d.text((200, 48), "这是一张演示截图", font=f_title, fill=(40, 44, 56), anchor="lm")
    d.rounded_rectangle([200, 84, 560, 96], radius=5, fill=(226, 229, 238))
    for i, wl in enumerate([500, 460, 520, 380, 430, 300]):
        y = 130 + i * 34
        d.rounded_rectangle([200, y, 200 + wl, y + 12], radius=5, fill=(226, 229, 238))
    d.rounded_rectangle([200, 360, 420, 430], radius=10, outline=(214, 216, 224), width=2)
    d.rounded_rectangle([216, 378, 320, 390], radius=5, fill=(179, 214, 175))
    d.rounded_rectangle([216, 400, 380, 412], radius=5, fill=(226, 229, 238))
    return im
