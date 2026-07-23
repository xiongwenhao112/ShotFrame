# -*- coding: utf-8 -*-
"""把处理结果图片写回 Windows 剪贴板（CF_DIB + PNG 双格式，零依赖）。

CF_DIB 保证微信/Word/QQ 等传统程序能贴，注册的 PNG 格式
让支持它的编辑器拿到无损版本。
"""
import ctypes
import io
import time
from ctypes import wintypes

CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def _win32():
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.EmptyClipboard.restype = wintypes.BOOL
    u32.CloseClipboard.restype = wintypes.BOOL
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    u32.RegisterClipboardFormatW.restype = wintypes.UINT
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    return u32, k32


def _to_global(k32, data):
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        raise OSError("GlobalAlloc 失败")
    p = k32.GlobalLock(h)
    if not p:
        k32.GlobalFree(h)
        raise OSError("GlobalLock 失败")
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    return h

def copy_image_to_clipboard(im, retries=5):
    """把 PIL Image 写入剪贴板。剪贴板被占用时重试几次。"""
    with io.BytesIO() as bio:
        im.convert("RGB").save(bio, "BMP")
        dib = bio.getvalue()[14:]          # 去掉 BITMAPFILEHEADER
    with io.BytesIO() as bio:
        im.save(bio, "PNG")
        png = bio.getvalue()

    u32, k32 = _win32()
    fmt_png = u32.RegisterClipboardFormatW("PNG")

    opened = False
    for _ in range(retries):
        if u32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        raise OSError("剪贴板被其他程序占用")
    try:
        u32.EmptyClipboard()
        for fmt, data in ((CF_DIB, dib), (fmt_png, png)):
            h = _to_global(k32, data)
            if not u32.SetClipboardData(fmt, h):
                k32.GlobalFree(h)
                raise OSError("SetClipboardData 失败 (fmt=%d)" % fmt)
    finally:
        u32.CloseClipboard()
