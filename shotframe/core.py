# -*- coding: utf-8 -*-
"""核心加框逻辑：把一张截图包装成「应用窗口卡片」。

设计目标：内容 100% 原样保留，只在外面加一圈明确的视觉包装，
让截图在图文正文里一眼可辨。
"""
import io
import os
import sys
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 样式

PRESETS = {
    "gray":   {"name": "浅灰", "bg": (241, 242, 246, 255)},
    "purple": {"name": "浅紫", "bg": (240, 238, 248, 255)},
    "blue":   {"name": "浅蓝", "bg": (235, 242, 250, 255)},
    "green":  {"name": "浅绿", "bg": (237, 245, 239, 255)},
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class FrameStyle:
    label: str = "实测截图"          # 标题栏文字，可为空
    preset: str = "gray"             # 底色预设 key
    show_dots: bool = True           # 是否画三个窗口圆点
    min_width: int = 200             # 小于该尺寸的图跳过（多为表情/图标）
    min_height: int = 100
    bar: tuple = (247, 248, 250, 255)
    hairline: tuple = (233, 234, 239, 255)
    border: tuple = (214, 216, 224, 255)
    label_color: tuple = (152, 160, 174, 255)
    shadow: tuple = (15, 23, 42, 60)
    dots: tuple = field(default=(
        (255, 95, 87, 255), (254, 188, 46, 255), (40, 200, 64, 255)))

    @property
    def bg(self):
        return PRESETS.get(self.preset, PRESETS["gray"])["bg"]


# ---------------------------------------------------------------- 字体

_FONT_CANDIDATES = [
    # Windows
    "msyh.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


def load_font(size):
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- 加框

def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def frame_image(im, style=None):
    """给一张 PIL Image 加窗口卡片，返回新的 RGB Image。"""
    style = style or FrameStyle()
    im = im.convert("RGB")
    w, h = im.size

    s = max(0.8, min(1.4, w / 1000.0))       # 随宽度缩放装饰元素
    mx = round(26 * s)                        # 左右留白
    myt = round(20 * s)                       # 顶部留白
    myb = round(34 * s)                       # 底部留白（含阴影余量）
    bar_h = round(38 * s)                     # 标题栏高
    radius = round(12 * s)
    blur = round(12 * s)
    dot_r = round(5.5 * s)
    font = load_font(round(15 * s))

    win_w, win_h = w, bar_h + h
    cw, ch = win_w + 2 * mx, win_h + myt + myb

    base = Image.new("RGBA", (cw, ch), style.bg)

    # 投影
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    off = round(5 * s)
    sd.rounded_rectangle(
        [mx, myt + off, mx + win_w - 1, myt + win_h - 1 + off],
        radius=radius, fill=style.shadow)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    base = Image.alpha_composite(base, sh)

    # 窗口本体 = 标题栏 + 截图
    win = Image.new("RGBA", (win_w, win_h), (255, 255, 255, 255))
    wd = ImageDraw.Draw(win)
    wd.rectangle([0, 0, win_w - 1, bar_h - 1], fill=style.bar)
    wd.rectangle([0, bar_h - 1, win_w - 1, bar_h - 1], fill=style.hairline)

    cx = round(20 * s)
    cy = bar_h // 2
    if style.show_dots:
        for color in style.dots:
            wd.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                       fill=color)
            cx += round(20 * s)
    if style.label:
        wd.text((cx + round(4 * s), cy), style.label,
                font=font, fill=style.label_color, anchor="lm")
    win.paste(im, (0, bar_h))

    base.paste(win, (mx, myt), _rounded_mask((win_w, win_h), radius))

    bd = ImageDraw.Draw(base)
    bd.rounded_rectangle(
        [mx, myt, mx + win_w - 1, myt + win_h - 1],
        radius=radius, outline=style.border, width=max(1, round(s)))
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
    dst = os.path.join(out_dir, base + ext)
    if ext in (".jpg", ".jpeg"):
        out.save(dst, "JPEG", quality=92)
    else:
        dst = os.path.join(out_dir, base + ".png")
        out.save(dst, "PNG", optimize=True)
    return dst


def frame_bytes(data, fmt_hint, style=None):
    """处理内存中的图片字节，返回 (新字节, 新宽, 新高)；跳过返回 None。"""
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
