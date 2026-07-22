# -*- coding: utf-8 -*-
"""docx 整篇处理：替换文档里的截图为加框版，并同步修正显示尺寸。"""
import os

from docx import Document
from docx.shared import Emu

from .core import FrameStyle, frame_bytes

_SKIP_EXTS = {".emf", ".wmf", ".gif", ".svg"}   # 矢量图/动图不处理


def process_docx(path, out_path=None, style=None, log=None):
    """处理 docx 内所有内嵌图片。

    返回 (输出路径, 处理张数, 跳过张数)。原文件不改动。
    """
    style = style or FrameStyle()
    log = log or (lambda msg: None)
    doc = Document(path)

    processed = {}    # partname -> (w, h) or None(跳过)
    done = skipped = 0

    for shape in doc.inline_shapes:
        try:
            rid = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
        except AttributeError:
            skipped += 1
            continue
        part = doc.part.related_parts[rid]
        pname = str(part.partname)
        ext = os.path.splitext(pname)[1].lower()

        if pname not in processed:
            if ext in _SKIP_EXTS:
                processed[pname] = None
                log("跳过（%s 格式）: %s" % (ext, os.path.basename(pname)))
            else:
                result = frame_bytes(part.blob, ext.lstrip("."), style)
                if result is None:
                    processed[pname] = None
                    log("跳过（尺寸过小）: %s" % os.path.basename(pname))
                else:
                    data, nw, nh = result
                    part._blob = data
                    processed[pname] = (nw, nh)
                    log("加框: %s -> %dx%d" % (os.path.basename(pname), nw, nh))

        info = processed[pname]
        if info is None:
            skipped += 1
            continue
        nw, nh = info
        shape.height = Emu(int(shape.width * nh / nw))
        done += 1

    if out_path is None:
        base, _ = os.path.splitext(path)
        out_path = base + "-加框.docx"
    doc.save(out_path)
    return out_path, done, skipped
