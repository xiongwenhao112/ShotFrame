# -*- coding: utf-8 -*-
"""GUI 集成测试 v0.3：队列模式全流程。

加文件入队 -> 不自动处理（断言）-> 切样式/自定义色 -> 点开始处理 ->
状态回写 -> 移除/清空 -> 退出。跑通打印 FLOW-OK 标记。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from shotframe.gui import App, CUSTOM_GRAD  # noqa: E402

from test_fixtures import ensure_fixtures, ensure_md_fixture  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG1, IMG9, _DOCX = ensure_fixtures()
MD = ensure_md_fixture()
MD_OUT = os.path.splitext(MD)[0] + "-加框.md"
OUT1 = os.path.join(HERE, "test_data", "加框", "image1.png")


def main():
    for f in (OUT1, MD_OUT):
        if os.path.exists(f):
            os.remove(f)
    app = App()

    def step_enqueue():
        app.add_paths([IMG1, IMG9, MD])
        n_wait = sum(1 for it in app.queue if it.status == "待处理")
        print("FLOW-OK enqueued 3, still waiting:", n_wait == 3,
              "not auto-processed:", not os.path.exists(OUT1))

    def step_paste():
        import shutil
        import shotframe.gui as G
        from shotframe.core import make_sample
        orig_grab = G.ImageGrab.grabclipboard
        # 分支1: 剪贴板是一张图
        G.ImageGrab.grabclipboard = lambda: make_sample(420, 280)
        n0 = len(app.queue)
        app._do_paste()
        pasted = [it for it in app.queue
                  if os.path.basename(it.path).startswith("剪贴板-")]
        ok_img = (len(app.queue) == n0 + 1 and len(pasted) == 1
                  and os.path.exists(pasted[0].path))
        app._pasted_files = [it.path for it in pasted]
        # 分支2: 剪贴板是复制的文件列表
        listfile = os.path.join(HERE, "test_data", "复制的文件.png")
        shutil.copy2(IMG1, listfile)
        G.ImageGrab.grabclipboard = lambda: [listfile]
        app._do_paste()
        ok_list = any(os.path.basename(it.path) == "复制的文件.png"
                      for it in app.queue)
        app._pasted_files.append(listfile)
        G.ImageGrab.grabclipboard = orig_grab   # 恢复，别污染后面的读回
        print("FLOW-OK paste image branch:", ok_img,
              "file branch:", ok_list)

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
              "img out:", os.path.exists(OUT1),
              "md out:", os.path.exists(MD_OUT))

        # 复制结果回剪贴板（真实剪贴板往返）
        from PIL import Image as _Img, ImageGrab as _Grab
        img_item = next(it for it in app.queue
                        if it.kind == "image" and it.out)
        app.select_item(img_item)
        app.copy_result()
        back = _Grab.grabclipboard()
        want = _Img.open(img_item.out).size
        ok_copy = back is not None and getattr(back, "size", None) == want
        md_item = next(it for it in app.queue if it.kind == "md")
        app.select_item(md_item)
        app.copy_result()
        ok_doc_msg = "文稿" in app.status_var.get()
        print("FLOW-OK copy result roundtrip:", ok_copy,
              "doc branch msg:", ok_doc_msg)

        # 移除一项 + 清空
        app.remove_item(app.queue[0])
        print("FLOW-OK removed one, left:", len(app.queue))
        app.clear_queue()
        print("FLOW-OK cleared, left:", len(app.queue))
        app.root.after(600, finish)

    def finish():
        # 清理粘贴产物（含加框输出）
        for f in getattr(app, "_pasted_files", []):
            for target in (f, os.path.join(os.path.dirname(f), "加框",
                                           os.path.basename(f))):
                if os.path.exists(target):
                    os.remove(target)
        print("FLOW-OK closing")
        app.on_close()

    app.root.after(600, step_enqueue)
    app.root.after(1200, step_paste)
    app.root.after(1800, step_style)
    app.root.after(2800, step_process)
    app.run()
    print("FLOW-OK exited cleanly")


if __name__ == "__main__":
    main()
