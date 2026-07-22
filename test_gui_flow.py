# -*- coding: utf-8 -*-
"""GUI 集成测试：切样式 -> 实时预览 -> 真实处理一张图 -> 退出。

跑通即打印 FLOW-OK 系列标记，供外部断言。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from shotframe.gui import App  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "test_data", "image1.png")
OUT = os.path.join(HERE, "test_data", "加框", "image1.png")


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    app = App()

    def step_style():
        app.frame_var.set("浏览器")
        app.backdrop_var.set("紫粉渐变")
        app.label_var.set("mp.weixin.qq.com")
        app.render_preview()
        print("FLOW-OK style-switched, preview rendered")

    def step_process():
        app.start([IMG])
        app.root.after(300, wait_done)

    def wait_done():
        if app.busy:
            app.root.after(300, wait_done)
            return
        ok = os.path.exists(OUT)
        print("FLOW-OK processed, output exists:", ok)
        app.root.after(1200, finish)

    def finish():
        print("FLOW-OK closing")
        app.on_close()

    app.root.after(700, step_style)
    app.root.after(1600, step_process)
    app.run()
    print("FLOW-OK exited cleanly")


if __name__ == "__main__":
    main()
