# -*- coding: utf-8 -*-
"""README 截图辅助：启动 GUI、预填队列、自己给自己截图后退出。"""
import ctypes
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PIL import ImageGrab  # noqa: E402

from shotframe.gui import App  # noqa: E402
from test_fixtures import ensure_fixtures  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG1, IMG9, DOCX = ensure_fixtures()
OUT = os.path.join(HERE, "assets", "screenshot-gui.png")


def main():
    app = App()
    root = app.root

    def fill():
        app.add_paths([IMG1, IMG9, DOCX])
        if app.queue:
            app.select_item(app.queue[0])

    def snap():
        try:
            root.attributes("-topmost", True)
            root.update()
            hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            im = ImageGrab.grab(bbox=(rect.left, rect.top,
                                      rect.right, rect.bottom))
            im.save(OUT)
            print("SAVED", OUT, im.size)
        except Exception as e:  # noqa: BLE001
            print("SNAP-FAIL", repr(e))
        finally:
            root.attributes("-topmost", False)
        root.after(400, root.destroy)

    import ctypes.wintypes  # noqa: E402  (确保 wintypes 已加载)

    root.after(600, fill)
    root.after(2600, snap)
    app.run()


if __name__ == "__main__":
    main()
