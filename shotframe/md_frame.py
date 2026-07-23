# -*- coding: utf-8 -*-
"""Markdown 整篇处理：给文中引用的本地图片加框，改写引用输出新 md。

规则：
- 支持 ![alt](path)、<img src="path">、[ref]: path 三种引用
- 只处理本地图片；http/https/data 引用跳过并记录
- 加框图与原图同目录，文件名加「-加框」后缀，原图不动
- 输出「原名-加框.md」，原 md 不动
"""
import os
import re
from urllib.parse import unquote

from PIL import Image

from .core import IMAGE_EXTS, FrameStyle, frame_image

_INLINE = re.compile(r'(!\[[^\]]*\]\()\s*(<[^>]+>|[^)\s]+)((?:\s+"[^"]*")?\s*\))')
_HTML = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*["\'])([^"\']+)(["\'])',
                   re.IGNORECASE)
_REFDEF = re.compile(r'(?m)^(\s*\[[^\]]+\]\s*:\s*)(\S+)(.*)$')

_REMOTE = ("http://", "https://", "data:", "//")


def _framed_name(path, style):
    base, ext = os.path.splitext(path)
    ext = ext.lower()
    out_ext = ext if ext in (".jpg", ".jpeg") else ".png"
    return base + "-加框" + out_ext


def process_markdown(path, out_path=None, style=None, log=None):
    """处理 md 内引用的本地图片。返回 (输出路径, 加框张数, 跳过张数)。"""
    style = style or FrameStyle()
    log = log or (lambda msg: None)
    md_dir = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()

    done_files = {}          # 原始引用串 -> 新引用串（None 表示跳过）
    stats = {"done": 0, "skip": 0}

    def resolve(ref):
        """处理一个引用，返回新引用串或 None。"""
        if ref in done_files:
            return done_files[ref]
        raw = ref.strip()
        wrapped = raw.startswith("<") and raw.endswith(">")
        inner = raw[1:-1] if wrapped else raw
        if inner.lower().startswith(_REMOTE):
            log("跳过（网络图片）: %s" % inner)
            done_files[ref] = None
            stats["skip"] += 1
            return None
        fs_path = unquote(inner)
        if not os.path.isabs(fs_path):
            fs_path = os.path.join(md_dir, fs_path)
        fs_path = os.path.normpath(fs_path)
        ext = os.path.splitext(fs_path)[1].lower()
        if ext not in IMAGE_EXTS:
            done_files[ref] = None
            return None
        if not os.path.exists(fs_path):
            log("跳过（找不到文件）: %s" % inner)
            done_files[ref] = None
            stats["skip"] += 1
            return None
        try:
            im = Image.open(fs_path)
        except OSError:
            log("跳过（无法打开）: %s" % inner)
            done_files[ref] = None
            stats["skip"] += 1
            return None
        if im.width < style.min_width or im.height < style.min_height:
            log("跳过（尺寸过小）: %s" % os.path.basename(fs_path))
            done_files[ref] = None
            stats["skip"] += 1
            return None
        out_file = _framed_name(fs_path, style)
        framed = frame_image(im, style)
        if out_file.lower().endswith((".jpg", ".jpeg")):
            framed.save(out_file, "JPEG", quality=92)
        else:
            framed.save(out_file, "PNG", optimize=True)
        stats["done"] += 1
        log("加框: %s -> %s" % (os.path.basename(fs_path),
                                os.path.basename(out_file)))
        # 引用串里只换文件名部分，目录前缀原样保留
        new_base = os.path.basename(out_file)
        slash = max(inner.rfind("/"), inner.rfind("\\"))
        new_inner = (inner[:slash + 1] + new_base) if slash >= 0 else new_base
        new_ref = ("<%s>" % new_inner) if wrapped else new_inner
        done_files[ref] = new_ref
        return new_ref

    def sub_inline(m):
        new = resolve(m.group(2))
        return m.group(1) + (new or m.group(2)) + m.group(3)

    def sub_html(m):
        new = resolve(m.group(2))
        return m.group(1) + (new or m.group(2)) + m.group(3)

    def sub_refdef(m):
        new = resolve(m.group(2))
        return m.group(1) + (new or m.group(2)) + m.group(3)

    text = _INLINE.sub(sub_inline, text)
    text = _HTML.sub(sub_html, text)
    text = _REFDEF.sub(sub_refdef, text)

    if out_path is None:
        base, ext = os.path.splitext(path)
        out_path = base + "-加框" + (ext or ".md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path, stats["done"], stats["skip"]
