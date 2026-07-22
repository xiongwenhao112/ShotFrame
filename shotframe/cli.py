# -*- coding: utf-8 -*-
"""命令行入口：ShotFrame 图片/文件夹/docx 批量加框。"""
import argparse
import os
import sys

from . import __version__
from .core import FrameStyle, IMAGE_EXTS, PRESETS, process_image_file
from .docx_frame import process_docx


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
                    elif ext == ".docx" and not f.startswith("~$"):
                        docs.append(full)
        elif os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in IMAGE_EXTS:
                images.append(p)
            elif ext == ".docx":
                docs.append(p)
            else:
                print("不支持的文件类型，已跳过:", p)
        else:
            print("找不到:", p)
    return images, docs


def build_style(args):
    return FrameStyle(
        label=("" if args.no_label else args.label),
        preset=args.preset,
        show_dots=not args.no_dots,
        min_width=args.min_width,
        min_height=args.min_height,
    )


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(
        prog="ShotFrame",
        description="给截图加窗口卡片边框，让读者一眼认出这是截图。"
                    "支持图片、文件夹和 docx 文稿。")
    parser.add_argument("paths", nargs="+", help="图片 / 文件夹 / docx 路径")
    parser.add_argument("--label", default="实测截图", help="标题栏文字，默认「实测截图」")
    parser.add_argument("--no-label", action="store_true", help="不显示标题栏文字")
    parser.add_argument("--preset", default="gray", choices=list(PRESETS),
                        help="底色预设: " + " ".join(
                            "%s(%s)" % (k, v["name"]) for k, v in PRESETS.items()))
    parser.add_argument("--no-dots", action="store_true", help="不画窗口圆点")
    parser.add_argument("--out", default=None, help="图片输出目录（默认输入旁的 加框/ 文件夹）")
    parser.add_argument("--recursive", action="store_true", help="文件夹递归处理")
    parser.add_argument("--min-width", type=int, default=200, help="小于该宽度跳过，默认200")
    parser.add_argument("--min-height", type=int, default=100, help="小于该高度跳过，默认100")
    parser.add_argument("--version", action="version", version="ShotFrame " + __version__)
    args = parser.parse_args(argv)

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
        out_path, done, skipped = process_docx(d, None, style, log=lambda m: print("  " + m))
        print("完成: %s（加框 %d 张，跳过 %d 张）" % (out_path, done, skipped))
        ok += done
        skip += skipped

    print("共加框 %d 张，跳过 %d 张。" % (ok, skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
