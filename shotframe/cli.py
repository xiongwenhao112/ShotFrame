# -*- coding: utf-8 -*-
"""命令行入口：ShotFrame 图片/文件夹/docx 批量加框。"""
import argparse
import os
import sys

from . import __version__
from .core import (BACKDROPS, FRAMES, IMAGE_EXTS, LEGACY_PRESETS, FrameStyle,
                   process_image_file)
from .docx_frame import process_docx
from .md_frame import process_markdown


def collect_inputs(paths, recursive=False):
    images, docs = [], []
    for p in paths:
        if os.path.isdir(p):
            walker = os.walk(p) if recursive else [(p, [], os.listdir(p))]
            for root, _dirs, files in walker:
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    full = os.path.join(root, f)
                    if ext in IMAGE_EXTS:
                        images.append(full)
                    elif ext in (".docx", ".md", ".markdown")                             and not f.startswith("~$"):
                        docs.append(full)
        elif os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in IMAGE_EXTS:
                images.append(p)
            elif ext in (".docx", ".md", ".markdown"):
                docs.append(p)
            else:
                print("不支持的文件类型，已跳过:", p)
        else:
            print("找不到:", p)
    return images, docs


def parse_bg_color(text):
    """解析 --bg-color: "#RRGGBB" 或 "#RRGGBB,#RRGGBB"（渐变）。"""
    parts = [p.strip().lstrip("#") for p in text.split(",") if p.strip()]
    colors = []
    for p in parts[:2]:
        if len(p) != 6:
            raise ValueError("颜色格式应为 #RRGGBB: " + p)
        colors.append(tuple(int(p[i:i + 2], 16) for i in (0, 2, 4)))
    if not colors:
        raise ValueError("没有解析到颜色: " + text)
    ctype = "gradient" if len(colors) == 2 else "solid"
    return ctype, tuple(colors)


def build_style(args):
    backdrop = args.bg
    custom_type, custom_colors = "solid", ((108, 92, 231), (236, 72, 153))
    if args.preset:                      # v0.1 兼容
        if args.preset in LEGACY_PRESETS:
            backdrop = args.preset
        print("提示: --preset 已改名为 --bg，本次按 --bg %s 处理" % backdrop)
    if args.bg_color:
        custom_type, custom_colors = parse_bg_color(args.bg_color)
        backdrop = "custom"
    return FrameStyle(
        frame=args.frame,
        backdrop=backdrop,
        custom_type=custom_type,
        custom_colors=custom_colors,
        label=("" if args.no_label else args.label),
        show_dots=not args.no_dots,
        pad=args.pad,
        radius=args.radius,
        shadow=args.shadow,
        watermark=args.watermark,
        min_width=args.min_width,
        min_height=args.min_height,
    )


def list_styles():
    print("窗口样式 (--frame):")
    for k, v in FRAMES.items():
        print("  %-10s %s" % (k, v["name"]))
    print("背景 (--bg):")
    for k, v in BACKDROPS.items():
        print("  %-12s %s" % (k, v["name"]))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(
        prog="ShotFrame",
        description="给截图加窗口卡片边框，让读者一眼认出这是截图。"
                    "支持图片、文件夹、docx 和 Markdown 文稿。")
    parser.add_argument("paths", nargs="*", help="图片 / 文件夹 / docx / md 路径")
    parser.add_argument("--frame", default="mac", choices=list(FRAMES),
                        help="窗口样式，默认 mac")
    parser.add_argument("--bg", default="gray", choices=list(BACKDROPS),
                        help="背景，默认 gray")
    parser.add_argument("--bg-color", default=None, metavar="#HEX[,#HEX]",
                        help="自定义背景色，一个色号为纯色，两个为渐变，"
                             "如 #FFE6C8 或 #6C5CE7,#EC4899")
    parser.add_argument("--pad", default="normal",
                        choices=["compact", "normal", "loose"],
                        help="留白档位，默认 normal")
    parser.add_argument("--radius", type=int, default=12,
                        help="圆角 0-24，默认 12")
    parser.add_argument("--shadow", type=int, default=60,
                        help="阴影强度 0-100，默认 60")
    parser.add_argument("--watermark", default="",
                        help="右下角水印文字，默认不加")
    parser.add_argument("--preset", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--label", default="实测截图",
                        help="标题栏/地址栏文字，默认「实测截图」")
    parser.add_argument("--no-label", action="store_true", help="不显示文字")
    parser.add_argument("--no-dots", action="store_true", help="不画窗口圆点")
    parser.add_argument("--out", default=None,
                        help="图片输出目录（默认输入旁的 加框/ 文件夹）")
    parser.add_argument("--recursive", action="store_true", help="文件夹递归处理")
    parser.add_argument("--min-width", type=int, default=200,
                        help="小于该宽度跳过，默认200")
    parser.add_argument("--min-height", type=int, default=100,
                        help="小于该高度跳过，默认100")
    parser.add_argument("--list-styles", action="store_true",
                        help="列出全部窗口样式与背景后退出")
    parser.add_argument("--version", action="version",
                        version="ShotFrame " + __version__)
    args = parser.parse_args(argv)

    if args.list_styles:
        list_styles()
        return 0
    if not args.paths:
        parser.print_usage()
        print("需要至少一个 图片 / 文件夹 / docx 路径，或用 --list-styles 查看样式。")
        return 1

    style = build_style(args)
    images, docs = collect_inputs(args.paths, args.recursive)
    if not images and not docs:
        print("没有找到可处理的图片或 docx。")
        return 1

    ok = skip = 0
    for img in images:
        dst = process_image_file(img, args.out, style)
        if dst is None:
            print("跳过（尺寸过小）:", img)
            skip += 1
        else:
            print("完成:", dst)
            ok += 1
    for d in docs:
        proc = process_docx if d.lower().endswith(".docx")             else process_markdown
        out_path, done, skipped = proc(
            d, None, style, log=lambda m: print("  " + m))
        print("完成: %s（加框 %d 张，跳过 %d 张）" % (out_path, done, skipped))
        ok += done
        skip += skipped

    print("共加框 %d 张，跳过 %d 张。" % (ok, skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
