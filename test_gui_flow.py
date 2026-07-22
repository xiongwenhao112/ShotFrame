# -*- coding: utf-8 -*-
"""GUI 集成测试 v0.3：队列模式全流程。

加文件入队 -> 不自动处理（断言）-> 切样式/自定义色 -> 点开始处理 ->
状态回写 -> 移除/清空 -> 退出。跑通打印 FLOW-OK 标记。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from shotframe.gui import App, CUSTOM_GRAD  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG1 = os.path.join(HERE, "test_data", "image1.png")
IMG9 = os.path.join(HERE, "test_data", "image9.png")
OUT1 = os.path.join(HERE, "test_data", "加框", "image1.png")


def main():
    if os.path.exists(OUT1):
        os.remove(OUT1)
    app = App()

    def step_enqueue():
        app.add_paths([IMG1, IMG9])
        n_wait = sum(1 for it in app.queue if it.status == "待处理")
        print("FLOW-OK enqueued 2, still waiting:", n_wait == 2,
              "not auto-processed:", not os.path.exists(OUT1))

    def step_style():
        app.frame_var.set("浏览器")
        app.backdrop_var.set(CUSTOM_GRAD)
        app.custom_c1 = (255, 94, 98)
        app.custom_c2 = (255, 195, 113)
        app.on_backdrop_change()
        app.label_var.set("mp.weixin.qq.com")
        app.wm_var.set("公众号 · 笃行其道")
        app.radius_var.set(18)
        app.shadow_var.set(80)
        app.render_preview()
        print("FLOW-OK style + custom gradient + watermark, preview rendered")

    def step_process():
        app.start_processing()
        print("FLOW-OK processing started, busy:", app.busy)
        app.root.after(300, wait_done)

    def wait_done():
        if app.busy:
            app.root.after(300, wait_done)
            return
        statuses = [it.status for it in app.queue]
        print("FLOW-OK done, statuses:", statuses,
              "output exists:", os.path.exists(OUT1))

        # 移除一项 + 清空
        app.remove_item(app.queue[0])
        print("FLOW-OK removed one, left:", len(app.queue))
        app.clear_queue()
        print("FLOW-OK cleared, left:", len(app.queue))
        app.root.after(600, finish)

    def finish():
        print("FLOW-OK closing")
        app.on_close()

    app.root.after(600, step_enqueue)
    app.root.after(1200, step_style)
    app.root.after(2200, step_process)
    app.run()
    print("FLOW-OK exited cleanly")


if __name__ == "__main__":
    main()
