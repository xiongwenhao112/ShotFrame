# -*- coding: utf-8 -*-
"""ShotFrame 全矩阵回归测试：样式组合、边界条件、docx 一致性。"""
import io
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image  # noqa: E402

from shotframe.core import (BACKDROPS, FRAMES, FrameStyle, frame_bytes,
                            frame_image, make_sample,
                            process_image_file)  # noqa: E402
from shotframe.docx_frame import process_docx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("[%s] %s %s" % (tag, name, detail))
    if not cond:
        FAILS.append(name)


def t_matrix():
    sample = make_sample(420, 260)
    n = 0
    for f in FRAMES:
        for b in BACKDROPS:
            for dots in (True, False):
                for label in ("实测截图", ""):
                    out = frame_image(sample, FrameStyle(
                        frame=f, backdrop=b, label=label, show_dots=dots))
                    assert out.width > 420 and out.height > 260
                    n += 1
    check("样式全矩阵渲染", n == len(FRAMES) * len(BACKDROPS) * 4,
          "%d 种组合" % n)


def t_edge_sizes():
    tiny = Image.new("RGB", (150, 80), (200, 200, 200))
    buf = io.BytesIO()
    tiny.save(buf, "PNG")
    check("小图跳过", frame_bytes(buf.getvalue(), "png") is None)

    tall = frame_image(Image.new("RGB", (250, 900), (230, 230, 230)),
                       FrameStyle(frame="browser"))
    check("竖长图渲染", tall.height > 900)

    wide = frame_image(Image.new("RGB", (2600, 320), (230, 230, 230)),
                       FrameStyle(frame="win11", backdrop="grad-ocean"))
    check("超宽图渲染", wide.width > 2600)


def t_jpg_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "photo.jpg")
        Image.new("RGB", (500, 300), (120, 140, 200)).save(src, "JPEG")
        dst = process_image_file(src, None, FrameStyle())
        check("jpg 保持 jpg 输出", dst is not None and dst.endswith(".jpg"))
        check("jpg 可打开", Image.open(dst).size[0] > 500)


def t_docx():
    from test_fixtures import ensure_fixtures, DOCX_IMAGES
    _i1, _i9, src = ensure_fixtures()
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "doc.docx")
        shutil.copy2(src, work)
        out_path, done, skipped = process_docx(
            work, None, FrameStyle(frame="win11", backdrop="purple"))
        check("docx 处理张数", done == DOCX_IMAGES,
              "done=%d skip=%d" % (done, skipped))
        # 校验显示比例与图片实际比例一致
        from docx import Document
        doc = Document(out_path)
        bad = 0
        for shape in doc.inline_shapes:
            rid = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
            part = doc.part.related_parts[rid]
            im = Image.open(io.BytesIO(part.blob))
            if abs(shape.width / shape.height - im.width / im.height) > 0.02:
                bad += 1
        check("docx 显示比例一致", bad == 0, "mismatch=%d" % bad)


def t_markdown():
    from shotframe.md_frame import process_markdown
    from shotframe.core import make_sample
    with tempfile.TemporaryDirectory() as td:
        imgdir = os.path.join(td, "assets")
        os.makedirs(imgdir)
        make_sample(500, 320).save(os.path.join(imgdir, "big.png"))
        Image.new("RGB", (100, 50), (200, 200, 200)).save(
            os.path.join(imgdir, "tiny.png"))
        md = os.path.join(td, "a.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("![b](assets/big.png)\n![b2](assets/big.png)\n"
                    "![t](assets/tiny.png)\n"
                    "![r](https://example.com/x.png)\n"
                    "![m](assets/missing.png)\n"
                    "<img src=\"assets/big.png\">\n")
        out, done, skipped = process_markdown(md)
        text = open(out, encoding="utf-8").read()
        check("md 加框张数", done == 1 and skipped == 3,
              "done=%d skip=%d" % (done, skipped))
        check("md 引用改写",
              text.count("assets/big-加框.png") == 3
              and "assets/tiny.png" in text
              and "https://example.com/x.png" in text)
        check("md 输出与原图保留",
              os.path.exists(out)
              and os.path.exists(os.path.join(imgdir, "big.png"))
              and os.path.exists(os.path.join(imgdir, "big-加框.png")))


def t_custom_and_params():
    sample = make_sample(420, 260)
    solid = frame_image(sample, FrameStyle(
        backdrop="custom", custom_type="solid",
        custom_colors=((255, 230, 200),), watermark="公众号 · 测试"))
    check("自定义纯色+水印", solid.width > 420)
    grad = frame_image(sample, FrameStyle(
        backdrop="custom", custom_type="gradient",
        custom_colors=((255, 94, 98), (255, 195, 113)),
        pad="loose", radius=24, shadow=100))
    check("自定义渐变+宽松+满圆角满阴影", grad.width > 420)
    flat = frame_image(sample, FrameStyle(pad="compact", radius=0, shadow=0))
    check("紧凑+零圆角+零阴影", flat.width > 420)
    # 深色自定义背景应用浅色水印分支
    dark = frame_image(sample, FrameStyle(
        backdrop="custom", custom_type="solid",
        custom_colors=((20, 22, 28),), watermark="dark"))
    check("深色自定义背景", dark.width > 420)


def t_cli():
    from shotframe.cli import main as cli_main
    check("CLI --list-styles", cli_main(["--list-styles"]) == 0)
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "a.png")
        Image.new("RGB", (400, 300), (240, 240, 240)).save(src)
        code = cli_main([src, "--frame", "plain", "--bg", "grad-sunset",
                         "--no-label", "--out", td])
        check("CLI 处理返回码", code == 0)
        check("CLI 输出存在", os.path.exists(os.path.join(td, "a.png")))
        code2 = cli_main([src, "--preset", "purple", "--out", td])
        check("CLI 旧参数兼容", code2 == 0)
        code3 = cli_main([src, "--bg-color", "#6C5CE7,#EC4899",
                          "--pad", "loose", "--radius", "20",
                          "--shadow", "90", "--watermark", "测试水印",
                          "--out", td])
        check("CLI 自定义色与新参数", code3 == 0)


def main():
    t_matrix()
    t_edge_sizes()
    t_jpg_roundtrip()
    t_docx()
    t_markdown()
    t_custom_and_params()
    t_cli()
    print("=" * 40)
    if FAILS:
        print("有 %d 项失败: %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
