# -*- coding: utf-8 -*-
"""ShotFrame 图形界面：办公软件风格布局，左侧设置 + 右侧实时预览。"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

from PIL import Image

from . import __version__
from .core import (BACKDROPS, FRAMES, IMAGE_EXTS, FrameStyle, frame_image,
                   make_sample, process_image_file)
from .docx_frame import process_docx

try:
    import customtkinter as ctk
    _HAS_CTK = True
except ImportError:
    _HAS_CTK = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

BRAND = "#6C5CE7"
BRAND_DARK = "#5A4BD1"
PAGE_BG = "#F2F3F7"
CARD_BG = "#FFFFFF"
TEXT_MAIN = "#2B2F3A"
TEXT_SUB = "#8A90A0"

CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ShotFrame")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

FRAME_BY_NAME = {v["name"]: k for k, v in FRAMES.items()}
BACKDROP_BY_NAME = {v["name"]: k for k, v in BACKDROPS.items()}


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


if _HAS_CTK and _HAS_DND:
    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.TkdndVersion = TkinterDnD._require(self)
elif _HAS_CTK:
    _Root = ctk.CTk
elif _HAS_DND:
    _Root = TkinterDnD.Tk
else:
    _Root = tk.Tk


class App:
    def __init__(self):
        if _HAS_CTK:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
        root = _Root()
        self.root = root
        root.title("ShotFrame · 截图加框")
        root.geometry("980x640")
        root.minsize(900, 580)
        if _HAS_CTK:
            root.configure(fg_color=PAGE_BG)
        self._set_icon()

        cfg = load_config()
        self.font = self._mkfont(13)
        self.font_small = self._mkfont(12)
        self.font_title = self._mkfont(15, "bold")

        self.sample = make_sample()
        self.preview_src = self.sample     # 预览用底图（拖入图片后换成真图）
        self._preview_job = None
        self.last_output = None
        self.busy = False

        self._build_header()
        self._build_body(cfg)
        self._build_footer()

        if _HAS_DND:
            for target in (root, self.drop_zone):
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self.on_drop)

        self.schedule_preview()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ 控件工厂

    @staticmethod
    def _mkfont(size, weight="normal"):
        if _HAS_CTK:
            return ctk.CTkFont(family="Microsoft YaHei UI", size=size,
                               weight=weight)
        return ("Microsoft YaHei UI", size, weight)

    def _set_icon(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        ico = os.path.join(base, "assets", "icon.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ 布局

    def _build_header(self):
        if not _HAS_CTK:
            return
        bar = ctk.CTkFrame(self.root, height=52, corner_radius=0,
                           fg_color=BRAND)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="ShotFrame", text_color="#FFFFFF",
                     font=self._mkfont(18, "bold")).pack(side="left", padx=(18, 6))
        ctk.CTkLabel(bar, text="截图加框 · 让截图一眼可辨", text_color="#D9D4FF",
                     font=self.font).pack(side="left")
        ctk.CTkLabel(bar, text="v" + __version__, text_color="#BDB4F5",
                     font=self.font_small).pack(side="right", padx=16)

    def _build_body(self, cfg):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ---- 左侧设置面板
        panel = ctk.CTkFrame(body, width=252, corner_radius=12,
                             fg_color=CARD_BG)
        panel.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        panel.grid_propagate(False)

        def section(text, pady=(16, 6)):
            ctk.CTkLabel(panel, text=text, text_color=TEXT_SUB,
                         font=self.font_small, anchor="w").pack(
                fill="x", padx=18, pady=pady)

        section("窗口样式", pady=(18, 6))
        self.frame_var = tk.StringVar(
            value=FRAMES.get(cfg.get("frame", "mac"), FRAMES["mac"])["name"])
        ctk.CTkSegmentedButton(
            panel, values=[v["name"] for v in FRAMES.values()],
            variable=self.frame_var, command=lambda _v: self.schedule_preview(),
            font=self.font_small, height=30).pack(fill="x", padx=16)

        section("背景")
        self.backdrop_var = tk.StringVar(
            value=BACKDROPS.get(cfg.get("backdrop", "gray"),
                                BACKDROPS["gray"])["name"])
        ctk.CTkOptionMenu(
            panel, values=[v["name"] for v in BACKDROPS.values()],
            variable=self.backdrop_var, command=lambda _v: self.schedule_preview(),
            font=self.font, dropdown_font=self.font, height=32,
            fg_color="#EEF0F6", button_color=BRAND, button_hover_color=BRAND_DARK,
            text_color=TEXT_MAIN).pack(fill="x", padx=16)

        section("标签文字（浏览器样式下为地址栏）")
        self.label_var = tk.StringVar(value=cfg.get("label", "实测截图"))
        entry = ctk.CTkEntry(panel, textvariable=self.label_var,
                             font=self.font, height=32)
        entry.pack(fill="x", padx=16)
        self.label_var.trace_add("write", lambda *_: self.schedule_preview())

        self.dots_var = tk.BooleanVar(value=cfg.get("dots", True))
        ctk.CTkSwitch(panel, text="窗口圆点", variable=self.dots_var,
                      command=self.schedule_preview, font=self.font,
                      progress_color=BRAND).pack(anchor="w", padx=18, pady=(16, 4))

        ctk.CTkLabel(panel, text="小于 200×100 的小图自动跳过\ndocx 会整篇处理并保持排版",
                     text_color=TEXT_SUB, font=self.font_small,
                     justify="left").pack(anchor="w", padx=18, pady=(14, 0))

        # ---- 右侧预览卡片
        right = ctk.CTkFrame(body, corner_radius=12, fg_color=CARD_BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(right, text="实时预览", text_color=TEXT_SUB,
                     font=self.font_small).grid(
            row=0, column=0, sticky="w", padx=18, pady=(12, 0))
        self.preview_label = ctk.CTkLabel(right, text="")
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=14, pady=10)
        right.bind("<Configure>", lambda _e: self.schedule_preview())

    def _build_footer(self):
        foot = ctk.CTkFrame(self.root, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(0, 12))
        foot.grid_columnconfigure(0, weight=1)

        # 拖放区
        self.drop_zone = ctk.CTkFrame(
            foot, height=76, corner_radius=12, fg_color="#EDEBFB",
            border_width=2, border_color="#C9C2F2")
        self.drop_zone.grid(row=0, column=0, sticky="ew")
        self.drop_zone.grid_propagate(False)
        self.drop_hint = ctk.CTkLabel(
            self.drop_zone,
            text="把 图片 / 文件夹 / docx 拖到这里，松手即开始处理" if _HAS_DND
            else "点击右侧按钮选择 图片 / 文件夹 / docx",
            text_color=BRAND_DARK, font=self.font)
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

        btns = ctk.CTkFrame(foot, fg_color="transparent")
        btns.grid(row=0, column=1, padx=(12, 0))
        self.pick_btn = ctk.CTkButton(
            btns, text="选择文件", command=self.browse, font=self.font,
            fg_color=BRAND, hover_color=BRAND_DARK, height=34, width=110)
        self.pick_btn.pack(pady=(0, 6))
        self.open_btn = ctk.CTkButton(
            btns, text="打开输出位置", command=self.open_output, font=self.font,
            fg_color="#E8E9F2", text_color=TEXT_MAIN, hover_color="#DCDEEA",
            height=34, width=110, state="disabled")
        self.open_btn.pack()

        # 日志
        self.log = ctk.CTkTextbox(
            foot, height=104, corner_radius=12, fg_color=CARD_BG,
            text_color=TEXT_MAIN, font=self.font_small, state="disabled")
        self.log.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.println("准备就绪。拖入文件，或点「选择文件」。")

    # ------------------------------------------------------------ 预览

    def current_style(self):
        return FrameStyle(
            frame=FRAME_BY_NAME.get(self.frame_var.get(), "mac"),
            backdrop=BACKDROP_BY_NAME.get(self.backdrop_var.get(), "gray"),
            label=self.label_var.get().strip(),
            show_dots=self.dots_var.get(),
            min_width=1, min_height=1,      # 预览不做尺寸过滤
        )

    def schedule_preview(self, *_args):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(120, self.render_preview)

    def render_preview(self):
        self._preview_job = None
        try:
            out = frame_image(self.preview_src, self.current_style())
            box_w = max(360, self.preview_label.winfo_width() - 8)
            box_h = max(260, self.preview_label.winfo_height() - 8)
            im = out.copy()
            im.thumbnail((box_w, box_h), Image.LANCZOS)
            self._preview_img = ctk.CTkImage(
                light_image=im, dark_image=im, size=im.size)
            self.preview_label.configure(image=self._preview_img, text="")
        except Exception as e:  # noqa: BLE001
            self.println("预览出错: %r" % (e,))

    # ------------------------------------------------------------ 事件

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
            "frame": FRAME_BY_NAME.get(self.frame_var.get(), "mac"),
            "backdrop": BACKDROP_BY_NAME.get(self.backdrop_var.get(), "gray"),
            "label": self.label_var.get(),
            "dots": self.dots_var.get(),
        })
        self.root.destroy()

    # ------------------------------------------------------------ 处理

    def println(self, msg):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _do)

    def set_busy(self, busy):
        def _do():
            self.busy = busy
            self.pick_btn.configure(state="disabled" if busy else "normal")
            self.drop_hint.configure(
                text="处理中，请稍候…" if busy else
                ("把 图片 / 文件夹 / docx 拖到这里，松手即开始处理" if _HAS_DND
                 else "点击右侧按钮选择 图片 / 文件夹 / docx"))
            if not busy and self.last_output:
                self.open_btn.configure(state="normal")
        self.root.after(0, _do)

    def start(self, paths):
        if self.busy or not paths:
            return
        style = self.current_style()
        style.min_width, style.min_height = 200, 100
        # 拖入的第一张图作为预览底图
        for p in paths:
            if os.path.splitext(p)[1].lower() in IMAGE_EXTS:
                try:
                    self.preview_src = Image.open(p).convert("RGB")
                    self.schedule_preview()
                except OSError:
                    pass
                break
        self.set_busy(True)
        threading.Thread(target=self.work, args=(paths, style),
                         daemon=True).start()

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
        self.set_busy(False)

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


# ---------------------------------------------------------------- 无 CTk 降级

class LegacyApp:
    """customtkinter 缺失时的极简回退界面（正常发行版不会走到这里）。"""

    def __init__(self):
        root = _Root()
        root.title("ShotFrame（简化界面，建议 pip install customtkinter）")
        root.geometry("520x300")
        self.root = root
        tk.Label(root, text="把文件路径粘贴到下面，一行一个，点处理",
                 font=("Microsoft YaHei UI", 11)).pack(pady=8)
        self.text = tk.Text(root, height=8)
        self.text.pack(fill="both", expand=True, padx=10)
        tk.Button(root, text="处理", command=self.go).pack(pady=8)

    def go(self):
        paths = [ln.strip() for ln in
                 self.text.get("1.0", "end").splitlines() if ln.strip()]
        style = FrameStyle()
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext == ".docx":
                process_docx(p, None, style)
            elif ext in IMAGE_EXTS:
                process_image_file(p, None, style)
        tk.messagebox.showinfo("ShotFrame", "处理完成")

    def run(self):
        self.root.mainloop()


def main():
    if _HAS_CTK:
        App().run()
    else:
        LegacyApp().run()


if __name__ == "__main__":
    main()
