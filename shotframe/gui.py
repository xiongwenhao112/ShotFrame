# -*- coding: utf-8 -*-
"""拖拽 GUI：把图片 / 文件夹 / docx 拖进窗口，一键加框。"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import __version__
from .core import FrameStyle, IMAGE_EXTS, PRESETS, process_image_file
from .docx_frame import process_docx

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ShotFrame")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

PRESET_BY_NAME = {v["name"]: k for k, v in PRESETS.items()}


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def split_dnd_paths(data):
    """tkinterdnd2 的路径串解析（带空格路径包在 {} 里）。"""
    paths, buf, brace = [], "", False
    for ch in data:
        if ch == "{":
            brace = True
        elif ch == "}":
            brace = False
            if buf:
                paths.append(buf)
                buf = ""
        elif ch == " " and not brace:
            if buf:
                paths.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        paths.append(buf)
    return paths


class App:
    def __init__(self):
        root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
        self.root = root
        root.title("ShotFrame · 截图加框 v" + __version__)
        root.geometry("620x560")
        root.minsize(560, 500)
        self._set_icon()

        cfg = load_config()

        # ---- 拖放区
        self.drop_var = tk.StringVar(value=self._drop_hint())
        drop = tk.Label(
            root, textvariable=self.drop_var, relief="groove", bd=2,
            fg="#666", bg="#F4F5F9", height=6, cursor="hand2",
            font=("Microsoft YaHei UI", 11))
        drop.pack(fill="x", padx=14, pady=(14, 8))
        drop.bind("<Button-1>", lambda e: self.browse())
        if _HAS_DND:
            drop.drop_target_register(DND_FILES)
            drop.dnd_bind("<<Drop>>", self.on_drop)

        # ---- 选项区
        opts = ttk.Frame(root)
        opts.pack(fill="x", padx=14)

        ttk.Label(opts, text="标签文字").grid(row=0, column=0, sticky="w")
        self.label_var = tk.StringVar(value=cfg.get("label", "实测截图"))
        ttk.Entry(opts, textvariable=self.label_var, width=18).grid(
            row=0, column=1, sticky="w", padx=(4, 16))

        ttk.Label(opts, text="底色").grid(row=0, column=2, sticky="w")
        self.preset_var = tk.StringVar(
            value=PRESETS.get(cfg.get("preset", "gray"), PRESETS["gray"])["name"])
        ttk.Combobox(
            opts, textvariable=self.preset_var, state="readonly", width=6,
            values=[v["name"] for v in PRESETS.values()]).grid(
            row=0, column=3, sticky="w", padx=(4, 16))

        self.dots_var = tk.BooleanVar(value=cfg.get("dots", True))
        ttk.Checkbutton(opts, text="窗口圆点", variable=self.dots_var).grid(
            row=0, column=4, sticky="w")

        # ---- 按钮行
        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=14, pady=8)
        self.go_btn = ttk.Button(btns, text="选择文件并加框", command=self.browse)
        self.go_btn.pack(side="left")
        self.open_btn = ttk.Button(
            btns, text="打开输出位置", command=self.open_output, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        ttk.Label(
            btns, text="小于 200×100 的小图会自动跳过", foreground="#999").pack(
            side="right")

        # ---- 日志区
        self.log = tk.Text(
            root, height=14, state="disabled", relief="flat", bg="#FAFAFC",
            font=("Microsoft YaHei UI", 9))
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.last_output = None
        self.busy = False
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_icon(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        ico = os.path.join(base, "assets", "icon.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
            except tk.TclError:
                pass

    @staticmethod
    def _drop_hint():
        if _HAS_DND:
            return "把 图片 / 文件夹 / docx 拖到这里\n（或点击选择文件）"
        return "点击这里选择 图片 / 文件夹 / docx\n（安装 tkinterdnd2 可启用拖拽）"

    # ---------------- 事件

    def on_drop(self, event):
        self.start(split_dnd_paths(event.data))

    def browse(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="选择图片或 docx",
            filetypes=[("图片或文稿", "*.png *.jpg *.jpeg *.webp *.bmp *.docx"),
                       ("所有文件", "*.*")])
        if paths:
            self.start(list(paths))

    def open_output(self):
        if not self.last_output:
            return
        target = self.last_output
        if os.path.isfile(target):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
        else:
            os.startfile(os.path.normpath(target))  # noqa: S606

    def on_close(self):
        save_config({
            "label": self.label_var.get(),
            "preset": PRESET_BY_NAME.get(self.preset_var.get(), "gray"),
            "dots": self.dots_var.get(),
        })
        self.root.destroy()

    # ---------------- 处理

    def println(self, msg):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _do)

    def start(self, paths):
        if self.busy or not paths:
            return
        self.busy = True
        self.go_btn.configure(state="disabled")
        self.drop_var.set("处理中…")
        style = FrameStyle(
            label=self.label_var.get().strip(),
            preset=PRESET_BY_NAME.get(self.preset_var.get(), "gray"),
            show_dots=self.dots_var.get(),
        )
        threading.Thread(target=self.work, args=(paths, style), daemon=True).start()

    def work(self, paths, style):
        ok = skip = 0
        try:
            for p in paths:
                p = p.strip()
                ext = os.path.splitext(p)[1].lower()
                if os.path.isdir(p):
                    for f in sorted(os.listdir(p)):
                        if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                            r = self._one_image(os.path.join(p, f), style)
                            ok, skip = ok + (r == 1), skip + (r == 0)
                elif ext in IMAGE_EXTS:
                    r = self._one_image(p, style)
                    ok, skip = ok + (r == 1), skip + (r == 0)
                elif ext == ".docx":
                    out_path, done, skipped = process_docx(
                        p, None, style, log=lambda m: self.println("  " + m))
                    self.println("完成: " + out_path)
                    self.last_output = out_path
                    ok += done
                    skip += skipped
                else:
                    self.println("跳过（不支持的类型）: " + p)
        except Exception as e:  # noqa: BLE001
            self.println("出错: %r" % (e,))
        self.println("—— 共加框 %d 张，跳过 %d 张 ——" % (ok, skip))

        def _done():
            self.busy = False
            self.go_btn.configure(state="normal")
            self.drop_var.set(self._drop_hint())
            if self.last_output:
                self.open_btn.configure(state="normal")
        self.root.after(0, _done)

    def _one_image(self, path, style):
        dst = process_image_file(path, None, style)
        if dst is None:
            self.println("跳过（尺寸过小）: " + os.path.basename(path))
            return 0
        self.println("完成: " + dst)
        self.last_output = os.path.dirname(dst)
        return 1

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
