# -*- coding: utf-8 -*-
"""窗口缩放稳定性测试：连续改变窗口尺寸后，面板布局必须在短时间内静止。

复现用户反馈：放大缩小窗口后，程序里每一块会自己动。
判定：最后一次缩放 0.8s 后开始采样 2s，各面板几何值的变化次数应为 0。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from shotframe.gui import App  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "test_data", "image9.png")

GEOMS = ["1080x700+80+40", "1360x840+60+30", "980x640+100+60",
         "1420x860+40+20", "1080x700+80+40"]
SETTLE_MS = 800          # 最后一次缩放后的允许安定期
SAMPLE_MS = 100
SAMPLES = 20             # 采样 2s


def main():
    import shotframe.gui as gui_mod
    real_frame_image = gui_mod.frame_image
    full_renders = {"n": 0}

    def counting_frame_image(*a, **k):
        full_renders["n"] += 1
        return real_frame_image(*a, **k)
    gui_mod.frame_image = counting_frame_image

    app = App()
    root = app.root
    app.add_paths([IMG])          # 带真实预览图，更接近用户场景
    if app.queue:
        app.select_item(app.queue[0])

    records = []
    storm_base = {"n": 0}

    # 连续小步缩放风暴：模拟用户拖拽，期间不应触发完整渲染
    def storm(step=0):
        if step == 0:
            storm_base["n"] = full_renders["n"]
        if step < 12:
            w = 1080 + step * 22
            root.geometry("%dx700+80+40" % w)
            root.after(60, lambda: storm(step + 1))
        else:
            storm_full = full_renders["n"] - storm_base["n"]
            print("风暴期间完整渲染次数: %d（快速路径应接管缩放）" % storm_full)
            print("STORM-" + ("PASS" if storm_full <= 1 else "FAIL"))

    def snapshot():
        try:
            return (
                app.preview_label.winfo_width(),
                app.preview_label.winfo_height(),
                app.queue_panel.winfo_rooty(),
                app.queue_panel.winfo_height(),
            )
        except Exception:  # noqa: BLE001
            return None

    # 阶段1: 风暴（等 1.2s 让首次渲染完成、缓存就位）
    root.after(1200, storm)
    # 阶段2: 依次大幅缩放
    for i, g in enumerate(GEOMS):
        root.after(2400 + i * 500, lambda gg=g: root.geometry(gg))

    t0 = 2400 + len(GEOMS) * 500 + SETTLE_MS

    def sample(n=0):
        records.append(snapshot())
        if n + 1 < SAMPLES:
            root.after(SAMPLE_MS, lambda: sample(n + 1))
        else:
            finish()

    def finish():
        distinct = []
        for r in records:
            if not distinct or r != distinct[-1]:
                distinct.append(r)
        changes = len(distinct) - 1
        print("采样 %d 次，安定期后布局变化次数: %d" % (len(records), changes))
        for d in distinct:
            print("  ", d)
        print("RESIZE-" + ("PASS" if changes == 0 else "FAIL"))
        root.after(300, root.destroy)

    root.after(t0, sample)
    app.run()


if __name__ == "__main__":
    main()
