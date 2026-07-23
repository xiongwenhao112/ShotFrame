# -*- coding: utf-8 -*-
"""ShotFrame 图形界面：办公软件风格（工具栏 + 分组面板 + 状态栏）。"""
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
from .md_frame import process_markdown

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

# ---------------- 办公风配色 ----------------
ACCENT = "#2468C2"          # 主蓝（按钮/选中）
ACCENT_DARK = "#1D549C"
PAGE_BG = "#ECEEF1"         # 窗体底
PANEL_BG = "#FFFFFF"        # 面板
PANEL_HEAD = "#F3F4F6"      # 面板标题条
TOOLBAR_BG = "#FAFBFC"
BORDER = "#D5D8DE"          # 1px 边框
HAIRLINE = "#EEF0F3"        # 行分隔
TEXT_MAIN = "#333A45"
TEXT_SUB = "#6B7482"
SELECT_BG = "#E8F0FB"       # 选中行
OK_GREEN = "#1E7E45"
ERR_RED = "#C23B3B"
R = 2                       # 全局圆角

REPO_URL = "https://github.com/xiongwenhao112/ShotFrame"

CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ShotFrame")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

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


def hex2rgb(s, default=(36, 104, 194)):
    try:
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return default


def rgb2hex(c):
    return "#%02X%02X%02X" % tuple(c)


def contrast_text(rgb):
    """按背景亮度返回黑/白文字色，保证色块上的字始终可读。"""
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return "#1F242D" if lum > 150 else "#FFFFFF"


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
        low = path.lower()
        if low.endswith(".docx"):
            self.kind = "docx"
        elif low.endswith((".md", ".markdown")):
            self.kind = "md"
        else:
            self.kind = "image"
        self.status = "待处理"
        self.note = ""
        self.row = None
        self.status_label = None


class App:
    def __init__(self):
        if _HAS_CTK:
            ctk.set_appearance_mode("light")
        root = _Root()
        self.root = root
        root.title("ShotFrame · 截图加框")
        root.geometry("1080x700")
        root.minsize(980, 620)
        root.configure(fg_color=PAGE_BG) if _HAS_CTK else None
        self._set_icon()

        cfg = load_config()
        self.f12 = self._mkfont(12)
        self.f12b = self._mkfont(12, "bold")
        self.f11 = self._mkfont(11)

        self.sample = make_sample()
        self.preview_src = self.sample
        self._preview_job = None
        self._fit_job = None
        self._frame_cache = None     # 全尺寸渲染缓存，缩放时只做快速缩略
        self.queue = []
        self.selected = None
        self.busy = False
        self.stop_flag = False
        self.last_output = None

        self.custom_c1 = hex2rgb(cfg.get("custom_c1", "#2468C2"))
        self.custom_c2 = hex2rgb(cfg.get("custom_c2", "#EC4899"))

        self._build_toolbar()
        self._build_body(cfg)
        self._build_statusbar()

        if _HAS_DND:
            for target in (root, self.queue_panel):
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self.on_drop)
            self.queue_panel.dnd_bind("<<DropEnter>>", self._drag_on)
            self.queue_panel.dnd_bind("<<DropLeave>>", self._drag_off)

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

    def _tool_btn(self, parent, text, command, primary=False, width=None):
        kw = dict(text=text, command=command, font=self.f12, height=28,
                  corner_radius=R)
        if width:
            kw["width"] = width
        if primary:
            kw.update(fg_color=ACCENT, hover_color=ACCENT_DARK,
                      text_color="#FFFFFF")
        else:
            kw.update(fg_color="transparent", hover_color="#E9ECF1",
                      text_color=TEXT_MAIN)
        return ctk.CTkButton(parent, **kw)

    @staticmethod
    def _divider(parent):
        f = ctk.CTkFrame(parent, width=1, height=20, fg_color="#D9DCE2",
                         corner_radius=0)
        f.pack(side="left", padx=6, pady=6)
        return f

    def _panel(self, parent, title):
        """带 1px 边框和标题条的分组面板，返回内容容器。"""
        outer = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=R,
                             border_width=1, border_color=BORDER)
        head = ctk.CTkFrame(outer, fg_color=PANEL_HEAD, corner_radius=0,
                            height=26)
        head.pack(fill="x", padx=1, pady=(1, 0))
        head.pack_propagate(False)
        ctk.CTkLabel(head, text=title, font=self.f12b,
                     text_color=TEXT_MAIN).pack(side="left", padx=8)
        body = ctk.CTkFrame(outer, fg_color=PANEL_BG, corner_radius=0)
        body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        outer.head = head
        outer.body = body
        return outer

    # ------------------------------------------------------------ 工具栏

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self.root, height=40, corner_radius=0,
                           fg_color=TOOLBAR_BG)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        line = ctk.CTkFrame(self.root, height=1, corner_radius=0,
                            fg_color=BORDER)
        line.pack(fill="x")

        self._tool_btn(bar, "添加文件", self.browse, width=76).pack(
            side="left", padx=(8, 2), pady=6)
        self._tool_btn(bar, "添加文件夹", self.browse_dir, width=88).pack(
            side="left", padx=2, pady=6)
        self.clear_btn = self._tool_btn(bar, "清空列表", self.clear_queue,
                                        width=76)
        self.clear_btn.pack(side="left", padx=2, pady=6)
        self._divider(bar)
        self.go_btn = self._tool_btn(bar, "开始处理", self.start_processing,
                                     primary=True, width=92)
        self.go_btn.pack(side="left", padx=2, pady=6)
        self.go_btn.configure(state="disabled")
        self.stop_btn = self._tool_btn(bar, "停止", self.stop_processing,
                                       width=56)
        self.stop_btn.pack(side="left", padx=2, pady=6)
        self.stop_btn.configure(state="disabled")
        self._divider(bar)
        self.open_btn = self._tool_btn(bar, "打开输出位置", self.open_output,
                                       width=100)
        self.open_btn.pack(side="left", padx=2, pady=6)
        self.open_btn.configure(state="disabled")

        self._tool_btn(bar, "关于", self.show_about, width=52).pack(
            side="right", padx=8, pady=6)

    # ------------------------------------------------------------ 主体

    def _build_body(self, cfg):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=5)
        body.grid_rowconfigure(1, weight=4)

        self._build_settings(body, cfg)

        pv = self._panel(body, "预览")
        pv.grid(row=0, column=1, sticky="nsew")
        self._build_preview(pv)

        qp = self._panel(body, "文件队列")
        qp.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        self.queue_panel = qp
        self._build_queue(qp)

    # ---- 设置面板
    def _build_settings(self, body, cfg):
        panel = self._panel(body, "样式设置")
        panel.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 8))
        wrap = ctk.CTkScrollableFrame(panel.body, width=252,
                                      fg_color=PANEL_BG, corner_radius=0)
        wrap.pack(fill="both", expand=True)

        def caption(text, pady=(12, 3)):
            ctk.CTkLabel(wrap, text=text, font=self.f11,
                         text_color=TEXT_SUB, anchor="w").pack(
                fill="x", padx=10, pady=pady)

        caption("窗口样式", pady=(8, 3))
        self.frame_var = tk.StringVar(
            value=FRAME_SHORT.get(cfg.get("frame", "mac"), "Mac浅"))
        ctk.CTkSegmentedButton(
            wrap, values=list(FRAME_SHORT.values()), variable=self.frame_var,
            command=lambda _v: self.schedule_preview(), font=self.f11,
            height=26, corner_radius=R, border_width=1,
            fg_color="#E4E7EC", selected_color="#CBDDF5",
            selected_hover_color="#BDD3F0", unselected_color="#F2F3F6",
            unselected_hover_color="#E7EAEF",
            text_color=TEXT_MAIN).pack(fill="x", padx=10)

        caption("背景")
        bd_key = cfg.get("backdrop", "gray")
        if bd_key == "custom":
            bd_name = CUSTOM_GRAD if cfg.get("custom_type") == "gradient" \
                else CUSTOM_SOLID
        else:
            bd_name = BACKDROPS.get(bd_key, BACKDROPS["gray"])["name"]
        self.backdrop_var = tk.StringVar(value=bd_name)
        self.backdrop_menu = ctk.CTkOptionMenu(
            wrap, values=BACKDROP_NAMES, variable=self.backdrop_var,
            command=lambda _v: self.on_backdrop_change(), font=self.f12,
            dropdown_font=self.f12, height=28, corner_radius=R,
            fg_color="#F2F3F6", button_color="#DDE1E8",
            button_hover_color="#CFD5DE",
            text_color=TEXT_MAIN)
        self.backdrop_menu.pack(fill="x", padx=10)

        self.color_row = ctk.CTkFrame(wrap, fg_color="transparent")
        self.c1_btn = ctk.CTkButton(
            self.color_row, text="颜色1", width=70, height=24, font=self.f11,
            corner_radius=R, border_width=1, border_color=BORDER,
            fg_color=rgb2hex(self.custom_c1),
            hover_color=rgb2hex(self.custom_c1),
            text_color=contrast_text(self.custom_c1),
            command=lambda: self.pick_color(1))
        self.c1_btn.pack(side="left", padx=(0, 6))
        self.c2_btn = ctk.CTkButton(
            self.color_row, text="颜色2", width=70, height=24, font=self.f11,
            corner_radius=R, border_width=1, border_color=BORDER,
            fg_color=rgb2hex(self.custom_c2),
            hover_color=rgb2hex(self.custom_c2),
            text_color=contrast_text(self.custom_c2),
            command=lambda: self.pick_color(2))
        self.c2_btn.pack(side="left")

        caption("留白")
        self.pad_var = tk.StringVar(
            value=PAD_NAMES.get(cfg.get("pad", "normal"), "标准"))
        ctk.CTkSegmentedButton(
            wrap, values=list(PAD_NAMES.values()), variable=self.pad_var,
            command=lambda _v: self.schedule_preview(), font=self.f11,
            height=26, corner_radius=R, border_width=1,
            fg_color="#E4E7EC", selected_color="#CBDDF5",
            selected_hover_color="#BDD3F0", unselected_color="#F2F3F6",
            unselected_hover_color="#E7EAEF",
            text_color=TEXT_MAIN).pack(fill="x", padx=10)

        self.radius_var = tk.IntVar(value=int(cfg.get("radius", 12)))
        self.shadow_var = tk.IntVar(value=int(cfg.get("shadow", 60)))
        caption("圆角")
        self._slider_row(wrap, self.radius_var, 0, 24, 24)
        caption("阴影")
        self._slider_row(wrap, self.shadow_var, 0, 100, 20)

        caption("标签文字（浏览器样式下为地址栏）")
        self.label_var = tk.StringVar(value=cfg.get("label", "实测截图"))
        ctk.CTkEntry(wrap, textvariable=self.label_var, font=self.f12,
                     height=28, corner_radius=R, border_width=1,
                     border_color=BORDER).pack(fill="x", padx=10)
        self.label_var.trace_add("write", lambda *_: self.schedule_preview())

        self.dots_var = tk.BooleanVar(value=cfg.get("dots", True))
        ctk.CTkCheckBox(
            wrap, text="窗口圆点", variable=self.dots_var,
            command=self.schedule_preview, font=self.f12,
            checkbox_width=16, checkbox_height=16, corner_radius=R,
            border_width=1, border_color="#9AA1AD", fg_color=ACCENT,
            hover_color=ACCENT_DARK).pack(anchor="w", padx=10, pady=(10, 0))

        caption("水印（右下角署名，留空不加）")
        self.wm_var = tk.StringVar(value=cfg.get("watermark", ""))
        ctk.CTkEntry(wrap, textvariable=self.wm_var, font=self.f12,
                     height=28, corner_radius=R, border_width=1,
                     border_color=BORDER,
                     placeholder_text="例如 公众号 · 笃行其道").pack(
            fill="x", padx=10)
        self.wm_var.trace_add("write", lambda *_: self.schedule_preview())

        caption("输出位置")
        self.out_mode = tk.StringVar(
            value="同目录加框文件夹" if cfg.get("out_mode", "sub") == "sub"
            else "自定义目录")
        ctk.CTkSegmentedButton(
            wrap, values=["同目录加框文件夹", "自定义目录"],
            variable=self.out_mode,
            command=lambda _v: self.on_outmode_change(), font=self.f11,
            height=26, corner_radius=R, border_width=1,
            fg_color="#E4E7EC", selected_color="#CBDDF5",
            selected_hover_color="#BDD3F0", unselected_color="#F2F3F6",
            unselected_hover_color="#E7EAEF",
            text_color=TEXT_MAIN).pack(fill="x", padx=10)
        self.out_dir = cfg.get("out_dir", "")
        self.out_btn = ctk.CTkButton(
            wrap, text=self._out_btn_text(), font=self.f11, height=26,
            corner_radius=R, border_width=1, border_color=BORDER,
            fg_color="#F2F3F6", text_color=TEXT_MAIN,
            hover_color="#E7EAEF", command=self.pick_out_dir)
        self.out_btn.pack(fill="x", padx=10, pady=(6, 10))
        self.on_outmode_change(init=True)

    def _slider_row(self, parent, var, lo, hi, steps):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10)
        val = ctk.CTkLabel(row, text=str(var.get()), font=self.f11,
                           text_color=TEXT_MAIN, width=28, anchor="e")
        val.pack(side="right")

        def on_change(_v):
            val.configure(text=str(int(var.get())))
            self.schedule_preview()
        ctk.CTkSlider(row, from_=lo, to=hi, number_of_steps=steps,
                      variable=var, height=14, corner_radius=R,
                      button_corner_radius=R, border_width=0,
                      progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color=ACCENT_DARK,
                      command=on_change).pack(side="left", fill="x",
                                              expand=True, padx=(0, 6))

    # ---- 预览面板
    def _build_preview(self, panel):
        self.preview_hint = ctk.CTkLabel(
            panel.head, text="点击队列中的图片可预览实图",
            text_color=TEXT_SUB, font=self.f11)
        self.preview_hint.pack(side="right", padx=8)
        # 固定容器：吸收图片尺寸变化，不把请求尺寸传回布局，
        # 否则「渲染->改变尺寸->触发重排->再渲染」会让面板自己动个不停
        self.preview_holder = ctk.CTkFrame(panel.body, fg_color=PANEL_BG,
                                           corner_radius=0)
        self.preview_holder.pack(fill="both", expand=True, padx=8, pady=8)
        self.preview_holder.pack_propagate(False)
        self.preview_label = ctk.CTkLabel(self.preview_holder, text="")
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")
        self._last_preview_box = (0, 0)
        self.preview_holder.bind("<Configure>", self._on_preview_resize)

    def _on_preview_resize(self, _e):
        w = self.preview_holder.winfo_width()
        h = self.preview_holder.winfo_height()
        lw, lh = self._last_preview_box
        if abs(w - lw) < 4 and abs(h - lh) < 4:
            return                      # 尺寸没有实质变化，不动
        if self._frame_cache is not None:
            # 缩放只走缓存快速路径：高频平滑跟随，不重跑加框管线
            if self._fit_job:
                self.root.after_cancel(self._fit_job)
            self._fit_job = self.root.after(30, self._fit_from_cache)
        else:
            self.schedule_preview()

    # ---- 队列面板（表格样式）
    def _build_queue(self, panel):
        self.queue_title_panel = panel
        # 表头
        header = ctk.CTkFrame(panel.body, fg_color=PANEL_HEAD,
                              corner_radius=0, height=24)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="文件名", font=self.f11,
                     text_color=TEXT_SUB, anchor="w").pack(
            side="left", fill="x", expand=True, padx=8)
        ctk.CTkLabel(header, text="状态", font=self.f11,
                     text_color=TEXT_SUB, width=90, anchor="e").pack(
            side="left", padx=4)
        ctk.CTkLabel(header, text="操作", font=self.f11,
                     text_color=TEXT_SUB, width=40, anchor="center").pack(
            side="left", padx=(2, 10))
        ctk.CTkFrame(panel.body, height=1, corner_radius=0,
                     fg_color=BORDER).pack(fill="x")

        self.queue_list = ctk.CTkScrollableFrame(
            panel.body, fg_color=PANEL_BG, corner_radius=0)
        self.queue_list.pack(fill="both", expand=True)
        self.empty_hint = ctk.CTkLabel(
            self.queue_list,
            text="将 图片 / 文件夹 / docx / md 拖入此处，或使用工具栏「添加文件」",
            text_color="#9AA1AD", font=self.f12)
        self.empty_hint.pack(pady=22)

        self.progress = ctk.CTkProgressBar(
            panel.body, height=6, corner_radius=0, progress_color=ACCENT,
            fg_color="#E4E7EC")
        self.progress.set(0)
        self.progress.pack(fill="x", side="bottom")

    def _build_statusbar(self):
        line = ctk.CTkFrame(self.root, height=1, corner_radius=0,
                            fg_color=BORDER)
        line.pack(fill="x", side="bottom")
        bar = ctk.CTkFrame(self.root, height=24, corner_radius=0,
                           fg_color=PANEL_HEAD)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(
            value="就绪。将文件加入队列后，点工具栏「开始处理」。")
        ctk.CTkLabel(bar, textvariable=self.status_var, font=self.f11,
                     text_color=TEXT_SUB, anchor="w").pack(
            side="left", fill="x", expand=True, padx=10)
        ctk.CTkLabel(bar, text="ShotFrame v" + __version__, font=self.f11,
                     text_color="#9AA1AD").pack(side="right", padx=10)

    # ------------------------------------------------------------ 设置联动

    def on_backdrop_change(self, *_):
        name = self.backdrop_var.get()
        if name in (CUSTOM_SOLID, CUSTOM_GRAD):
            # 紧跟在背景下拉框后面，而不是掉到面板末尾
            self.color_row.pack(fill="x", padx=10, pady=(6, 0),
                                after=self.backdrop_menu)
            self.c2_btn.configure(
                state="normal" if name == CUSTOM_GRAD else "disabled")
        else:
            self.color_row.pack_forget()
        self.schedule_preview()

    def pick_color(self, which):
        cur = self.custom_c1 if which == 1 else self.custom_c2
        rgb, _hex = colorchooser.askcolor(
            color=rgb2hex(cur), title="选择颜色 %d" % which, parent=self.root)
        if rgb is None:
            return
        rgb = tuple(int(v) for v in rgb)
        if which == 1:
            self.custom_c1 = rgb
            self.c1_btn.configure(fg_color=rgb2hex(rgb),
                                  hover_color=rgb2hex(rgb),
                                  text_color=contrast_text(rgb))
        else:
            self.custom_c2 = rgb
            self.c2_btn.configure(fg_color=rgb2hex(rgb),
                                  hover_color=rgb2hex(rgb),
                                  text_color=contrast_text(rgb))
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
            if len(short) > 30:
                short = "…" + short[-29:]
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
        """样式或图片变化：作废缓存，安排一次完整渲染。"""
        self._frame_cache = None
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(120, self.render_preview)

    def render_preview(self):
        self._preview_job = None
        w = self.preview_holder.winfo_width()
        h = self.preview_holder.winfo_height()
        # 窗口尚未完成布局时稍后重试，避免启动瞬间渲染出空白预览
        if w < 60 or h < 60:
            self._preview_job = self.root.after(250, self.render_preview)
            return
        try:
            self._frame_cache = frame_image(
                self.preview_src, self.current_style(for_preview=True))
        except Exception as e:  # noqa: BLE001
            self.status_var.set("预览出错: %r" % (e,))
            return
        self._fit_from_cache()

    def _fit_from_cache(self):
        """从全尺寸缓存快速缩放到当前容器，拖动缩放走这条廉价路径。"""
        self._fit_job = None
        if self._frame_cache is None:
            return
        w = self.preview_holder.winfo_width()
        h = self.preview_holder.winfo_height()
        if w < 60 or h < 60:
            return
        self._last_preview_box = (w, h)
        im = self._frame_cache.copy()
        im.thumbnail((max(120, w - 8), max(120, h - 8)), Image.LANCZOS)
        self._preview_img = ctk.CTkImage(light_image=im, dark_image=im,
                                         size=im.size)
        self.preview_label.configure(image=self._preview_img, text="")

    # ------------------------------------------------------------ 队列

    def _drag_on(self, _e):
        self.queue_panel.configure(border_color=ACCENT)

    def _drag_off(self, _e):
        self.queue_panel.configure(border_color=BORDER)

    def on_drop(self, event):
        self._drag_off(None)
        self.add_paths(split_dnd_paths(event.data))

    def browse(self):
        paths = filedialog.askopenfilenames(
            title="选择图片、docx 或 Markdown",
            filetypes=[("图片或文稿",
                       "*.png *.jpg *.jpeg *.webp *.bmp *.docx *.md"),
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
                    if (ext in IMAGE_EXTS
                            or ext in (".docx", ".md", ".markdown")) \
                            and not f.startswith("~$") \
                            and full not in existing:
                        self._append_item(full)
                        existing.add(full)
                        added += 1
            elif os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if (ext in IMAGE_EXTS
                        or ext in (".docx", ".md", ".markdown")) \
                        and p not in existing:
                    self._append_item(p)
                    existing.add(p)
                    added += 1
        if added:
            self.status_var.set("已加入 %d 个文件，点工具栏「开始处理」。" % added)
            first_img = next((it for it in self.queue
                              if it.kind == "image"), None)
            if first_img and self.selected is None:
                self.select_item(first_img)
        self._refresh_queue_ui()

    def _append_item(self, path):
        item = QueueItem(path)
        self.queue.append(item)
        row = ctk.CTkFrame(self.queue_list, fg_color=PANEL_BG,
                           corner_radius=0)
        row.pack(fill="x")
        item.row = row
        tag = {"docx": "docx", "md": "md  "}.get(item.kind, "img ")
        name = ctk.CTkLabel(
            row, text=" [%s] %s" % (tag, os.path.basename(path)),
            font=self.f12, text_color=TEXT_MAIN, anchor="w")
        name.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=2)
        item.status_label = ctk.CTkLabel(
            row, text=item.status, font=self.f11, text_color=TEXT_SUB,
            width=90, anchor="e")
        item.status_label.pack(side="left", padx=4)
        rm = ctk.CTkButton(row, text="移除", width=40, height=20,
                           font=self.f11, corner_radius=R,
                           fg_color="transparent", text_color=TEXT_SUB,
                           hover_color="#E9ECF1",
                           command=lambda it=item: self.remove_item(it))
        rm.pack(side="left", padx=(2, 10))
        sep = ctk.CTkFrame(self.queue_list, height=1, corner_radius=0,
                           fg_color=HAIRLINE)
        sep.pack(fill="x")
        item.note = ""
        row.sep = sep
        for widget in (row, name):
            widget.bind("<Button-1>", lambda _e, it=item: self.select_item(it))

    def select_item(self, item):
        self.selected = item
        for it in self.queue:
            if it.row:
                it.row.configure(fg_color=SELECT_BG if it is item
                                 else PANEL_BG)
        if item.kind == "image":
            try:
                self.preview_src = Image.open(item.path).convert("RGB")
                self.preview_hint.configure(
                    text="预览：%s" % os.path.basename(item.path))
            except OSError:
                self.preview_src = self.sample
        else:
            self.preview_src = self.sample
            self.preview_hint.configure(text="文稿将整篇处理，预览为示意图")
        self.schedule_preview()

    def remove_item(self, item):
        if self.busy:
            return
        if item.row:
            if hasattr(item.row, "sep"):
                item.row.sep.destroy()
            item.row.destroy()
        self.queue.remove(item)
        if self.selected is item:
            self.selected = None
            self.preview_src = self.sample
            self.preview_hint.configure(text="点击队列中的图片可预览实图")
            self.schedule_preview()
        self._refresh_queue_ui()

    def clear_queue(self):
        if self.busy:
            return
        for it in self.queue:
            if it.row:
                if hasattr(it.row, "sep"):
                    it.row.sep.destroy()
                it.row.destroy()
        self.queue.clear()
        self.selected = None
        self.preview_src = self.sample
        self.preview_hint.configure(text="点击队列中的图片可预览实图")
        self.progress.set(0)
        self._refresh_queue_ui()
        self.schedule_preview()

    def _refresh_queue_ui(self):
        n = len(self.queue)
        for w in self.queue_title_panel.head.winfo_children():
            if isinstance(w, ctk.CTkLabel):
                w.configure(text="文件队列（%d）" % n)
                break
        if n == 0:
            self.empty_hint.pack(pady=22)
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
        threading.Thread(target=self.work,
                         args=(list(self.queue), style, out_dir),
                         daemon=True).start()

    def stop_processing(self):
        self.stop_flag = True
        self.status_var.set("正在停止…完成当前文件后停下。")

    def set_busy(self, busy):
        def _do():
            self.busy = busy
            self.go_btn.configure(
                state="disabled" if (busy or not self.queue) else "normal",
                text="处理中…" if busy else "开始处理")
            self.stop_btn.configure(state="normal" if busy else "disabled")
            self.clear_btn.configure(state="disabled" if busy else "normal")
            if not busy and self.last_output:
                self.open_btn.configure(state="normal")
            for it in self.queue:
                if it.row:
                    for child in it.row.winfo_children():
                        if isinstance(child, ctk.CTkButton):
                            child.configure(
                                state="disabled" if busy else "normal")
        self.root.after(0, _do)

    def work(self, items, style, out_dir):
        total = len(items)
        ok = skip = fail = 0
        for i, item in enumerate(items):
            if self.stop_flag:
                self._set_item_status(item, "已取消", TEXT_SUB)
                continue
            self._set_item_status(item, "处理中…", ACCENT_DARK)
            try:
                if item.kind == "image":
                    dst = process_image_file(item.path, out_dir, style)
                    if dst is None:
                        skip += 1
                        self._set_item_status(item, "跳过·小图", TEXT_SUB)
                    else:
                        ok += 1
                        self.last_output = os.path.dirname(dst)
                        self._set_item_status(item, "完成", OK_GREEN)
                else:
                    out_path = None
                    suffix = ".docx" if item.kind == "docx" else                         os.path.splitext(item.path)[1]
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                        base = os.path.splitext(
                            os.path.basename(item.path))[0]
                        out_path = os.path.join(out_dir,
                                                base + "-加框" + suffix)
                    proc = process_docx if item.kind == "docx"                         else process_markdown
                    dst, done, skipped = proc(
                        item.path, out_path, style, log=lambda m: None)
                    ok += done
                    skip += skipped
                    self.last_output = dst
                    self._set_item_status(item, "完成 %d张" % done, OK_GREEN,
                                          "跳过%d" % skipped)
            except Exception as e:  # noqa: BLE001
                fail += 1
                self._set_item_status(item, "失败", ERR_RED, repr(e))
                self.root.after(0, lambda err=e, p=item.path:
                                self.status_var.set("失败 %s: %r" % (
                                    os.path.basename(p), err)))
            self.root.after(0, lambda v=(i + 1) / total: self.progress.set(v))
        summary = "完成。加框 %d 张，跳过 %d 张" % (ok, skip)
        if fail:
            summary += "，失败 %d 个" % fail
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
        win.geometry("380x220")
        win.resizable(False, False)
        win.transient(self.root)
        win.configure(fg_color=PANEL_BG)
        ctk.CTkLabel(win, text="ShotFrame · 截图加框",
                     font=self._mkfont(15, "bold"),
                     text_color=TEXT_MAIN).pack(pady=(24, 4))
        ctk.CTkLabel(win, text="v%s · MIT 开源 · 离线运行" % __version__,
                     font=self.f11, text_color=TEXT_SUB).pack()
        ctk.CTkLabel(
            win, font=self.f11, text_color=TEXT_SUB, justify="center",
            text="给公众号 / 知乎 / 博客作者的截图美化工具\n"
                 "5 种窗口框 × 预设与自定义背景 × docx/Markdown 整篇处理").pack(pady=8)
        ctk.CTkButton(win, text="打开开源主页", font=self.f12,
                      corner_radius=R, fg_color=ACCENT,
                      hover_color=ACCENT_DARK, height=28,
                      command=lambda: webbrowser.open(REPO_URL)).pack(pady=8)

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
