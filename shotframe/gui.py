# -*- coding: utf-8 -*-
"""ShotFrame 图形界面 v0.3：文件队列 + 处理按钮 + 自定义样式。

布局：品牌头部 / 左设置面板 / 右上实时预览 / 右下文件队列 / 底部状态栏。
"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog

from PIL import Image

from . import __version__
from .core import (BACKDROPS, FRAMES, IMAGE_EXTS, PAD_NAMES, FrameStyle,
                   frame_image, make_sample, process_image_file)
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
OK_GREEN = "#1FA95C"
ERR_RED = "#D64545"

REPO_URL = "https://github.com/duxingqidao/ShotFrame"

CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ShotFrame")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

FRAME_BY_NAME = {v["name"]: k for k, v in FRAMES.items()}
# 分段按钮空间有限，用短名显示
FRAME_SHORT = {"mac": "Mac浅", "mac-dark": "Mac深", "win11": "Win11",
               "browser": "浏览器", "plain": "极简"}
FRAME_BY_SHORT = {v: k for k, v in FRAME_SHORT.items()}
PAD_BY_NAME = {v: k for k, v in PAD_NAMES.items()}
CUSTOM_SOLID = "自定义纯色"
CUSTOM_GRAD = "自定义渐变"
BACKDROP_NAMES = [v["name"] for v in BACKDROPS.values()] + [CUSTOM_SOLID,
                                                            CUSTOM_GRAD]
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


def hex2rgb(s, default=(108, 92, 231)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return default


def rgb2hex(c):
    return "#%02X%02X%02X" % tuple(c)


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


class QueueItem:
    __slots__ = ("path", "kind", "status", "row", "status_label", "note")

    def __init__(self, path):
        self.path = path
        self.kind = "docx" if path.lower().endswith(".docx") else "image"
        self.status = "待处理"
        self.note = ""
        self.row = None
        self.status_label = None


class App:
    def __init__(self):
        if _HAS_CTK:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
        root = _Root()
        self.root = root
        root.title("ShotFrame · 截图加框")
        root.geometry("1080x700")
        root.minsize(980, 640)
        if _HAS_CTK:
            root.configure(fg_color=PAGE_BG)
        self._set_icon()

        cfg = load_config()
        self.font = self._mkfont(13)
        self.font_small = self._mkfont(12)

        self.sample = make_sample()
        self.preview_src = self.sample
        self._preview_job = None
        self.queue = []                 # list[QueueItem]
        self.selected = None            # QueueItem
        self.busy = False
        self.stop_flag = False
        self.last_output = None

        self.custom_c1 = hex2rgb(cfg.get("custom_c1", "#6C5CE7"))
        self.custom_c2 = hex2rgb(cfg.get("custom_c2", "#EC4899"))

        self._build_header()
        self._build_body(cfg)
        self._build_statusbar()

        if _HAS_DND:
            for target in (root, self.queue_card):
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self.on_drop)
            self.queue_card.dnd_bind("<<DropEnter>>", self._drag_on)
            self.queue_card.dnd_bind("<<DropLeave>>", self._drag_off)

        self.on_backdrop_change()
        self.schedule_preview()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ 基础

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

    # ------------------------------------------------------------ 头部

    def _build_header(self):
        bar = ctk.CTkFrame(self.root, height=52, corner_radius=0,
                           fg_color=BRAND)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="ShotFrame", text_color="#FFFFFF",
                     font=self._mkfont(18, "bold")).pack(side="left",
                                                         padx=(18, 6))
        ctk.CTkLabel(bar, text="截图加框 · 让截图一眼可辨",
                     text_color="#D9D4FF", font=self.font).pack(side="left")
        ctk.CTkButton(bar, text="关于", width=56, height=26,
                      fg_color="#8578EC", hover_color=BRAND_DARK,
                      font=self.font_small, command=self.show_about).pack(
            side="right", padx=14)
        ctk.CTkLabel(bar, text="v" + __version__, text_color="#BDB4F5",
                     font=self.font_small).pack(side="right", padx=4)

    # ------------------------------------------------------------ 主体

    def _build_body(self, cfg):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=5)
        body.grid_rowconfigure(1, weight=4)

        self._build_settings(body, cfg)
        self._build_preview(body)
        self._build_queue(body)

    # ---- 左：设置面板
    def _build_settings(self, body, cfg):
        panel = ctk.CTkScrollableFrame(
            body, width=270, corner_radius=12, fg_color=CARD_BG)
        panel.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 12))

        def section(text, pady=(14, 4)):
            ctk.CTkLabel(panel, text=text, text_color=TEXT_SUB,
                         font=self.font_small, anchor="w").pack(
                fill="x", padx=14, pady=pady)

        section("窗口样式", pady=(10, 4))
        self.frame_var = tk.StringVar(
            value=FRAME_SHORT.get(cfg.get("frame", "mac"), "Mac浅"))
        ctk.CTkSegmentedButton(
            panel, values=list(FRAME_SHORT.values()),
            variable=self.frame_var, command=lambda _v: self.schedule_preview(),
            font=self.font_small, height=30).pack(fill="x", padx=12)

        section("背景")
        bd_key = cfg.get("backdrop", "gray")
        if bd_key == "custom":
            bd_name = CUSTOM_GRAD if cfg.get("custom_type") == "gradient" \
                else CUSTOM_SOLID
        else:
            bd_name = BACKDROPS.get(bd_key, BACKDROPS["gray"])["name"]
        self.backdrop_var = tk.StringVar(value=bd_name)
        ctk.CTkOptionMenu(
            panel, values=BACKDROP_NAMES, variable=self.backdrop_var,
            command=lambda _v: self.on_backdrop_change(),
            font=self.font, dropdown_font=self.font, height=32,
            fg_color="#EEF0F6", button_color=BRAND,
            button_hover_color=BRAND_DARK, text_color=TEXT_MAIN).pack(
            fill="x", padx=12)

        self.color_row = ctk.CTkFrame(panel, fg_color="transparent")
        self.c1_btn = ctk.CTkButton(
            self.color_row, text="颜色 1", width=76, height=28,
            font=self.font_small, fg_color=rgb2hex(self.custom_c1),
            hover_color=rgb2hex(self.custom_c1),
            command=lambda: self.pick_color(1))
        self.c1_btn.pack(side="left", padx=(0, 8))
        self.c2_btn = ctk.CTkButton(
            self.color_row, text="颜色 2", width=76, height=28,
            font=self.font_small, fg_color=rgb2hex(self.custom_c2),
            hover_color=rgb2hex(self.custom_c2),
            command=lambda: self.pick_color(2))
        self.c2_btn.pack(side="left")

        section("留白")
        self.pad_var = tk.StringVar(
            value=PAD_NAMES.get(cfg.get("pad", "normal"), "标准"))
        ctk.CTkSegmentedButton(
            panel, values=list(PAD_NAMES.values()), variable=self.pad_var,
            command=lambda _v: self.schedule_preview(),
            font=self.font_small, height=28).pack(fill="x", padx=12)

        section("圆角 / 阴影")
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=12)
        self.radius_var = tk.IntVar(value=int(cfg.get("radius", 12)))
        self.shadow_var = tk.IntVar(value=int(cfg.get("shadow", 60)))
        ctk.CTkLabel(row, text="圆角", font=self.font_small,
                     text_color=TEXT_SUB, width=30).grid(row=0, column=0)
        ctk.CTkSlider(row, from_=0, to=24, number_of_steps=24,
                      variable=self.radius_var, progress_color=BRAND,
                      command=lambda _v: self.schedule_preview()).grid(
            row=0, column=1, sticky="ew", padx=6)
        ctk.CTkLabel(row, text="阴影", font=self.font_small,
                     text_color=TEXT_SUB, width=30).grid(row=1, column=0)
        ctk.CTkSlider(row, from_=0, to=100, number_of_steps=20,
                      variable=self.shadow_var, progress_color=BRAND,
                      command=lambda _v: self.schedule_preview()).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        row.grid_columnconfigure(1, weight=1)

        section("标签文字（浏览器样式下为地址栏）")
        self.label_var = tk.StringVar(value=cfg.get("label", "实测截图"))
        ctk.CTkEntry(panel, textvariable=self.label_var, font=self.font,
                     height=32).pack(fill="x", padx=12)
        self.label_var.trace_add("write", lambda *_: self.schedule_preview())

        self.dots_var = tk.BooleanVar(value=cfg.get("dots", True))
        ctk.CTkSwitch(panel, text="窗口圆点", variable=self.dots_var,
                      command=self.schedule_preview, font=self.font,
                      progress_color=BRAND).pack(anchor="w", padx=14,
                                                 pady=(12, 0))

        section("水印（右下角署名，留空不加）")
        self.wm_var = tk.StringVar(value=cfg.get("watermark", ""))
        wm = ctk.CTkEntry(panel, textvariable=self.wm_var, font=self.font,
                          height=32, placeholder_text="例如 公众号 · 笃行其道")
        wm.pack(fill="x", padx=12)
        self.wm_var.trace_add("write", lambda *_: self.schedule_preview())

        section("输出位置")
        self.out_mode = tk.StringVar(value=cfg.get("out_mode", "sub"))
        ctk.CTkSegmentedButton(
            panel, values=["同目录加框文件夹", "自定义目录"],
            variable=self.out_mode,
            command=lambda _v: self.on_outmode_change(),
            font=self.font_small, height=28).pack(fill="x", padx=12)
        self.out_mode.set("同目录加框文件夹" if cfg.get("out_mode", "sub") == "sub"
                          else "自定义目录")
        self.out_dir = cfg.get("out_dir", "")
        self.out_btn = ctk.CTkButton(
            panel, text=self._out_btn_text(), font=self.font_small,
            fg_color="#EEF0F6", text_color=TEXT_MAIN, hover_color="#E2E4EE",
            height=28, command=self.pick_out_dir)
        self.out_btn.pack(fill="x", padx=12, pady=(6, 12))
        self.on_outmode_change(init=True)

    # ---- 右上：预览
    def _build_preview(self, body):
        right = ctk.CTkFrame(body, corner_radius=12, fg_color=CARD_BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        ctk.CTkLabel(head, text="实时预览", text_color=TEXT_SUB,
                     font=self.font_small).pack(side="left")
        self.preview_hint = ctk.CTkLabel(
            head, text="（点击队列中的图片可预览实图）",
            text_color="#B8BdCa", font=self.font_small)
        self.preview_hint.pack(side="left", padx=6)
        self.preview_label = ctk.CTkLabel(right, text="")
        self.preview_label.grid(row=1, column=0, sticky="nsew",
                                padx=12, pady=(4, 10))
        right.bind("<Configure>", lambda _e: self.schedule_preview())

    # ---- 右下：文件队列
    def _build_queue(self, body):
        card = ctk.CTkFrame(body, corner_radius=12, fg_color=CARD_BG,
                            border_width=2, border_color=CARD_BG)
        card.grid(row=1, column=1, sticky="nsew", pady=(10, 0))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.queue_card = card

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.queue_title = ctk.CTkLabel(
            head, text="文件队列（0）", text_color=TEXT_SUB,
            font=self.font_small)
        self.queue_title.pack(side="left")
        ctk.CTkButton(head, text="清空", width=52, height=24,
                      font=self.font_small, fg_color="#EEF0F6",
                      text_color=TEXT_MAIN, hover_color="#E2E4EE",
                      command=self.clear_queue).pack(side="right", padx=(6, 0))
        ctk.CTkButton(head, text="添加文件夹", width=76, height=24,
                      font=self.font_small, fg_color="#EEF0F6",
                      text_color=TEXT_MAIN, hover_color="#E2E4EE",
                      command=self.browse_dir).pack(side="right", padx=(6, 0))
        ctk.CTkButton(head, text="添加文件", width=68, height=24,
                      font=self.font_small, fg_color="#EEF0F6",
                      text_color=TEXT_MAIN, hover_color="#E2E4EE",
                      command=self.browse).pack(side="right")

        self.queue_list = ctk.CTkScrollableFrame(
            card, fg_color="#F7F8FB", corner_radius=8)
        self.queue_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        self.empty_hint = ctk.CTkLabel(
            self.queue_list,
            text="把 图片 / 文件夹 / docx 拖到这里\n或点右上「添加文件」",
            text_color="#A9AEBE", font=self.font)
        self.empty_hint.pack(pady=26)

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 10))
        foot.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(foot, height=8,
                                           progress_color=BRAND)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.stop_btn = ctk.CTkButton(
            foot, text="停止", width=64, height=34, font=self.font,
            fg_color="#EEF0F6", text_color=TEXT_MAIN, hover_color="#E2E4EE",
            state="disabled", command=self.stop_processing)
        self.stop_btn.grid(row=0, column=1, padx=(0, 8))
        self.open_btn = ctk.CTkButton(
            foot, text="打开输出位置", width=100, height=34, font=self.font,
            fg_color="#EEF0F6", text_color=TEXT_MAIN, hover_color="#E2E4EE",
            state="disabled", command=self.open_output)
        self.open_btn.grid(row=0, column=2, padx=(0, 8))
        self.go_btn = ctk.CTkButton(
            foot, text="开始处理", width=120, height=34,
            font=self._mkfont(14, "bold"), fg_color=BRAND,
            hover_color=BRAND_DARK, state="disabled",
            command=self.start_processing)
        self.go_btn.grid(row=0, column=3)

    def _build_statusbar(self):
        self.status_var = tk.StringVar(
            value="准备就绪。拖入文件加入队列，点「开始处理」。")
        ctk.CTkLabel(self.root, textvariable=self.status_var,
                     text_color=TEXT_SUB, font=self.font_small,
                     anchor="w").pack(fill="x", padx=20, pady=(0, 8))

    # ------------------------------------------------------------ 设置联动

    def on_backdrop_change(self, *_):
        name = self.backdrop_var.get()
        if name in (CUSTOM_SOLID, CUSTOM_GRAD):
            self.color_row.pack(fill="x", padx=12, pady=(6, 0))
            self.c2_btn.configure(
                state="normal" if name == CUSTOM_GRAD else "disabled")
        else:
            self.color_row.pack_forget()
        self.schedule_preview()

    def pick_color(self, which):
        cur = self.custom_c1 if which == 1 else self.custom_c2
        rgb, _hex = colorchooser.askcolor(
            color=rgb2hex(cur), title="选择颜色 %d" % which,
            parent=self.root)
        if rgb is None:
            return
        rgb = tuple(int(v) for v in rgb)
        if which == 1:
            self.custom_c1 = rgb
            self.c1_btn.configure(fg_color=rgb2hex(rgb),
                                  hover_color=rgb2hex(rgb))
        else:
            self.custom_c2 = rgb
            self.c2_btn.configure(fg_color=rgb2hex(rgb),
                                  hover_color=rgb2hex(rgb))
        self.schedule_preview()

    def on_outmode_change(self, init=False):
        custom = self.out_mode.get() == "自定义目录"
        self.out_btn.configure(state="normal" if custom else "disabled",
                               text=self._out_btn_text())
        if custom and not self.out_dir and not init:
            self.pick_out_dir()

    def _out_btn_text(self):
        if self.out_dir:
            short = self.out_dir
            if len(short) > 28:
                short = "…" + short[-27:]
            return short
        return "点击选择输出目录"

    def pick_out_dir(self):
        d = filedialog.askdirectory(title="选择输出目录", parent=self.root)
        if d:
            self.out_dir = os.path.normpath(d)
            self.out_btn.configure(text=self._out_btn_text())

    def current_style(self, for_preview=False):
        name = self.backdrop_var.get()
        if name == CUSTOM_SOLID:
            backdrop, ctype = "custom", "solid"
        elif name == CUSTOM_GRAD:
            backdrop, ctype = "custom", "gradient"
        else:
            backdrop, ctype = BACKDROP_BY_NAME.get(name, "gray"), "solid"
        return FrameStyle(
            frame=FRAME_BY_SHORT.get(self.frame_var.get(), "mac"),
            backdrop=backdrop,
            custom_type=ctype,
            custom_colors=(self.custom_c1, self.custom_c2),
            label=self.label_var.get().strip(),
            show_dots=self.dots_var.get(),
            pad=PAD_BY_NAME.get(self.pad_var.get(), "normal"),
            radius=self.radius_var.get(),
            shadow=self.shadow_var.get(),
            watermark=self.wm_var.get().strip(),
            min_width=1 if for_preview else 200,
            min_height=1 if for_preview else 100,
        )

    # ------------------------------------------------------------ 预览

    def schedule_preview(self, *_):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(120, self.render_preview)

    def render_preview(self):
        self._preview_job = None
        try:
            out = frame_image(self.preview_src,
                              self.current_style(for_preview=True))
            box_w = max(360, self.preview_label.winfo_width() - 8)
            box_h = max(220, self.preview_label.winfo_height() - 8)
            im = out.copy()
            im.thumbnail((box_w, box_h), Image.LANCZOS)
            self._preview_img = ctk.CTkImage(light_image=im, dark_image=im,
                                             size=im.size)
            self.preview_label.configure(image=self._preview_img, text="")
        except Exception as e:  # noqa: BLE001
            self.status_var.set("预览出错: %r" % (e,))

    # ------------------------------------------------------------ 队列

    def _drag_on(self, _e):
        self.queue_card.configure(border_color=BRAND)

    def _drag_off(self, _e):
        self.queue_card.configure(border_color=CARD_BG)

    def on_drop(self, event):
        self._drag_off(None)
        self.add_paths(split_dnd_paths(event.data))

    def browse(self):
        paths = filedialog.askopenfilenames(
            title="选择图片或 docx",
            filetypes=[("图片或文稿", "*.png *.jpg *.jpeg *.webp *.bmp *.docx"),
                       ("所有文件", "*.*")])
        if paths:
            self.add_paths(list(paths))

    def browse_dir(self):
        d = filedialog.askdirectory(title="选择文件夹")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        if self.busy:
            self.status_var.set("处理中，稍后再添加。")
            return
        added = 0
        existing = {it.path for it in self.queue}
        for p in paths:
            p = os.path.normpath(p.strip())
            if os.path.isdir(p):
                for f in sorted(os.listdir(p)):
                    ext = os.path.splitext(f)[1].lower()
                    full = os.path.join(p, f)
                    if (ext in IMAGE_EXTS or ext == ".docx") \
                            and not f.startswith("~$") \
                            and full not in existing:
                        self._append_item(full)
                        existing.add(full)
                        added += 1
            elif os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if (ext in IMAGE_EXTS or ext == ".docx") \
                        and p not in existing:
                    self._append_item(p)
                    existing.add(p)
                    added += 1
        if added:
            self.status_var.set("已加入 %d 个文件，点「开始处理」。" % added)
            first_img = next((it for it in self.queue
                              if it.kind == "image"), None)
            if first_img and self.selected is None:
                self.select_item(first_img)
        self._refresh_queue_ui()

    def _append_item(self, path):
        item = QueueItem(path)
        self.queue.append(item)
        row = ctk.CTkFrame(self.queue_list, fg_color="#FFFFFF",
                           corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)
        item.row = row
        icon = "📄" if item.kind == "docx" else "🖼"
        name = ctk.CTkLabel(
            row, text="%s  %s" % (icon, os.path.basename(path)),
            font=self.font_small, text_color=TEXT_MAIN, anchor="w")
        name.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=3)
        item.status_label = ctk.CTkLabel(
            row, text=item.status, font=self.font_small,
            text_color=TEXT_SUB, width=88, anchor="e")
        item.status_label.pack(side="left", padx=4)
        rm = ctk.CTkButton(row, text="✕", width=24, height=22,
                           font=self.font_small, fg_color="#F1F2F6",
                           text_color=TEXT_SUB, hover_color="#E2E4EE",
                           command=lambda it=item: self.remove_item(it))
        rm.pack(side="left", padx=(2, 6))
        for widget in (row, name):
            widget.bind("<Button-1>", lambda _e, it=item: self.select_item(it))

    def select_item(self, item):
        self.selected = item
        for it in self.queue:
            if it.row:
                it.row.configure(fg_color="#EDEBFB" if it is item
                                 else "#FFFFFF")
        if item.kind == "image":
            try:
                self.preview_src = Image.open(item.path).convert("RGB")
                self.preview_hint.configure(
                    text="（预览：%s）" % os.path.basename(item.path))
            except OSError:
                self.preview_src = self.sample
        else:
            self.preview_src = self.sample
            self.preview_hint.configure(text="（docx 将整篇处理，预览为示意图）")
        self.schedule_preview()

    def remove_item(self, item):
        if self.busy:
            return
        if item.row:
            item.row.destroy()
        self.queue.remove(item)
        if self.selected is item:
            self.selected = None
            self.preview_src = self.sample
            self.preview_hint.configure(text="（点击队列中的图片可预览实图）")
            self.schedule_preview()
        self._refresh_queue_ui()

    def clear_queue(self):
        if self.busy:
            return
        for it in self.queue:
            if it.row:
                it.row.destroy()
        self.queue.clear()
        self.selected = None
        self.preview_src = self.sample
        self.preview_hint.configure(text="（点击队列中的图片可预览实图）")
        self.progress.set(0)
        self._refresh_queue_ui()
        self.schedule_preview()

    def _refresh_queue_ui(self):
        n = len(self.queue)
        self.queue_title.configure(text="文件队列（%d）" % n)
        if n == 0:
            self.empty_hint.pack(pady=26)
        else:
            self.empty_hint.pack_forget()
        self.go_btn.configure(
            state="normal" if (n and not self.busy) else "disabled")

    def _set_item_status(self, item, status, color=TEXT_SUB, note=""):
        def _do():
            item.status = status
            item.note = note
            if item.status_label:
                item.status_label.configure(text=status, text_color=color)
        self.root.after(0, _do)

    # ------------------------------------------------------------ 处理

    def start_processing(self):
        if self.busy or not self.queue:
            return
        style = self.current_style()
        out_dir = self.out_dir if (self.out_mode.get() == "自定义目录"
                                   and self.out_dir) else None
        self.stop_flag = False
        self.set_busy(True)
        threading.Thread(target=self.work, args=(list(self.queue), style,
                                                 out_dir),
                         daemon=True).start()

    def stop_processing(self):
        self.stop_flag = True
        self.status_var.set("正在停止…完成当前文件后停下。")

    def set_busy(self, busy):
        def _do():
            self.busy = busy
            state_run = "disabled" if busy else "normal"
            self.go_btn.configure(
                state="disabled" if (busy or not self.queue) else "normal",
                text="处理中…" if busy else "开始处理")
            self.stop_btn.configure(state="normal" if busy else "disabled")
            if not busy and self.last_output:
                self.open_btn.configure(state="normal")
            for it in self.queue:
                if it.row:
                    for child in it.row.winfo_children():
                        if isinstance(child, ctk.CTkButton):
                            child.configure(state=state_run)
        self.root.after(0, _do)

    def work(self, items, style, out_dir):
        total = len(items)
        ok = skip = fail = 0
        for i, item in enumerate(items):
            if self.stop_flag:
                self._set_item_status(item, "已取消", TEXT_SUB)
                continue
            self._set_item_status(item, "处理中…", BRAND_DARK)
            try:
                if item.kind == "image":
                    dst = process_image_file(item.path, out_dir, style)
                    if dst is None:
                        skip += 1
                        self._set_item_status(item, "跳过·小图", TEXT_SUB)
                    else:
                        ok += 1
                        self.last_output = os.path.dirname(dst)
                        self._set_item_status(item, "✓ 完成", OK_GREEN)
                else:
                    out_path = None
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                        base = os.path.splitext(
                            os.path.basename(item.path))[0]
                        out_path = os.path.join(out_dir, base + "-加框.docx")
                    dst, done, skipped = process_docx(
                        item.path, out_path, style, log=lambda m: None)
                    ok += done
                    skip += skipped
                    self.last_output = dst
                    self._set_item_status(
                        item, "✓ %d张" % done, OK_GREEN,
                        "跳过%d" % skipped)
            except Exception as e:  # noqa: BLE001
                fail += 1
                self._set_item_status(item, "✗ 失败", ERR_RED, repr(e))
                self.root.after(0, lambda err=e, p=item.path: self.status_var.set(
                    "失败 %s: %r" % (os.path.basename(p), err)))
            self.root.after(0, lambda v=(i + 1) / total: self.progress.set(v))
        summary = "完成。加框 %d 张，跳过 %d 张" % (ok, skip)
        if fail:
            summary += "，失败 %d 个（见队列状态）" % fail
        if self.stop_flag:
            summary = "已停止。" + summary
        self.root.after(0, lambda: self.status_var.set(summary))
        self.set_busy(False)

    # ------------------------------------------------------------ 其他

    def open_output(self):
        if not self.last_output:
            return
        target = self.last_output
        if os.path.isfile(target):
            subprocess.Popen(["explorer", "/select,",
                              os.path.normpath(target)])
        else:
            os.startfile(os.path.normpath(target))  # noqa: S606

    def show_about(self):
        win = ctk.CTkToplevel(self.root)
        win.title("关于 ShotFrame")
        win.geometry("380x230")
        win.resizable(False, False)
        win.transient(self.root)
        ctk.CTkLabel(win, text="ShotFrame · 截图加框",
                     font=self._mkfont(16, "bold")).pack(pady=(22, 4))
        ctk.CTkLabel(win, text="v%s · MIT 开源 · 离线运行" % __version__,
                     font=self.font_small,
                     text_color=TEXT_SUB).pack()
        ctk.CTkLabel(
            win, font=self.font_small, text_color=TEXT_SUB, justify="center",
            text="给公众号 / 知乎 / 博客作者的截图美化工具\n"
                 "5 种窗口框 × 预设与自定义背景 × docx 整篇处理").pack(pady=10)
        ctk.CTkButton(win, text="打开开源主页", font=self.font, fg_color=BRAND,
                      hover_color=BRAND_DARK,
                      command=lambda: webbrowser.open(REPO_URL)).pack(pady=6)

    def on_close(self):
        name = self.backdrop_var.get()
        if name == CUSTOM_SOLID:
            backdrop, ctype = "custom", "solid"
        elif name == CUSTOM_GRAD:
            backdrop, ctype = "custom", "gradient"
        else:
            backdrop, ctype = BACKDROP_BY_NAME.get(name, "gray"), "solid"
        save_config({
            "frame": FRAME_BY_SHORT.get(self.frame_var.get(), "mac"),
            "backdrop": backdrop,
            "custom_type": ctype,
            "custom_c1": rgb2hex(self.custom_c1),
            "custom_c2": rgb2hex(self.custom_c2),
            "label": self.label_var.get(),
            "dots": self.dots_var.get(),
            "pad": PAD_BY_NAME.get(self.pad_var.get(), "normal"),
            "radius": self.radius_var.get(),
            "shadow": self.shadow_var.get(),
            "watermark": self.wm_var.get(),
            "out_mode": "custom" if self.out_mode.get() == "自定义目录"
                        else "sub",
            "out_dir": self.out_dir,
        })
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------- 降级

class LegacyApp:
    """customtkinter 缺失时的极简回退界面。"""

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
        from tkinter import messagebox
        style = FrameStyle()
        for p in [ln.strip() for ln in
                  self.text.get("1.0", "end").splitlines() if ln.strip()]:
            ext = os.path.splitext(p)[1].lower()
            if ext == ".docx":
                process_docx(p, None, style)
            elif ext in IMAGE_EXTS:
                process_image_file(p, None, style)
        messagebox.showinfo("ShotFrame", "处理完成")

    def run(self):
        self.root.mainloop()


def main():
    if _HAS_CTK:
        App().run()
    else:
        LegacyApp().run()


if __name__ == "__main__":
    main()
