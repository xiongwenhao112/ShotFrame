# -*- coding: utf-8 -*-
"""生成 ShotFrame 图标：紫底圆角卡片 + 窗口条 + 三个圆点。"""
import os

from PIL import Image, ImageDraw


def draw(size):
    s = size / 256.0
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # 背景圆角方块
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s],
                        radius=48 * s, fill=(108, 92, 231, 255))
    # 白色窗口卡片
    d.rounded_rectangle([48 * s, 64 * s, 208 * s, 192 * s],
                        radius=20 * s, fill=(255, 255, 255, 255))
    # 标题栏
    d.rounded_rectangle([48 * s, 64 * s, 208 * s, 104 * s],
                        radius=20 * s, fill=(240, 241, 246, 255))
    d.rectangle([48 * s, 88 * s, 208 * s, 104 * s], fill=(240, 241, 246, 255))
    # 三个圆点
    for i, color in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        cx = (68 + i * 26) * s
        d.ellipse([cx - 7 * s, 84 * s - 7 * s, cx + 7 * s, 84 * s + 7 * s],
                  fill=color + (255,))
    # 内容线条
    for i, w in enumerate([120, 96, 108]):
        y = (124 + i * 22) * s
        d.rounded_rectangle([64 * s, y, (64 + w) * s, y + 10 * s],
                            radius=5 * s, fill=(203, 208, 220, 255))
    return im


def main():
    os.makedirs("assets", exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(sz) for sz in sizes]
    imgs[-1].save("assets/icon.ico", sizes=[(sz, sz) for sz in sizes],
                  append_images=imgs[:-1])
    imgs[-1].save("assets/icon.png")
    print("icon written to assets/")


if __name__ == "__main__":
    main()
