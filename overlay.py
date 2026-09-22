"""全屏截图覆盖层：紧凑工具栏（对标 QQ 截图）。"""

from __future__ import annotations

import ctypes
import math
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

import clipboard_win

# 工具
T_SELECT = "select"
T_RECT = "rect"
T_ELLIPSE = "ellipse"
T_ARROW = "arrow"
T_PEN = "pen"
T_TEXT = "text"
T_SEQ = "seq"          # 序号标注
T_MOSAIC = "mosaic"
T_BLUR = "blur"
T_PICKER = "picker"

COLORS = ["#ff3b30", "#ffcc00", "#34c759", "#007aff", "#000000", "#ffffff"]
WIDTHS = [2, 4, 8]

MAG_ZOOM = 8
MAG_SIZE = 136
HANDLE = 8
PANEL_STEP = 64       # 选区高亮面板的分配台阶（越大换图越少，但边角越粗）
PANEL_REFRESH_MS = 90  # 拖动中面板内容的刷新间隔：外框每帧跟手，亮块按此节流

# 工具中文名（悬停提示 / 状态栏共用）
TOOL_NAMES = {
    T_SELECT: "选择",
    T_RECT: "矩形",
    T_ELLIPSE: "椭圆",
    T_ARROW: "箭头",
    T_PEN: "画笔",
    T_TEXT: "文字",
    T_SEQ: "序号",
    T_MOSAIC: "马赛克",
    T_BLUR: "模糊",
    T_PICKER: "取色",
}

# 悬停提示（名称 · 用法）
TOOL_TIPS = {
    T_SELECT: "选择 · 拖动边角/内部调整选区",
    T_RECT: "矩形 · 拖动绘制",
    T_ELLIPSE: "椭圆 · 拖动绘制",
    T_ARROW: "箭头 · 拖动绘制",
    T_PEN: "画笔 · 按住自由绘制，滚轮调粗细",
    T_TEXT: "文字 · 点击画面输入",
    T_SEQ: "序号 · 点击添加 ①②③",
    T_MOSAIC: "马赛克 · 拖动涂抹",
    T_BLUR: "模糊 · 拖动涂抹",
    T_PICKER: "取色 · 点击画面取色",
}


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------- 工具栏图标（对标 QQ 截图的线性图标） ----------
# 用 PIL 画再降采样，得到抗锯齿的矢量感图标；字体图标（▭ ◯ ➤）在不同机器上
# 会因字体缺失而变成方框，且无法统一线宽与视觉重量，所以改成自己画。

_ICON_SS = 4          # 超采样倍数
_ICON_CACHE: dict[tuple[str, str, int], "Image.Image"] = {}


def _icon_px() -> int:
    """图标逻辑边长，跟随系统 DPI（上限 32px，避免高缩放屏上过大）。"""
    dpi = 96
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem() or 96
    except Exception:
        pass
    return max(14, min(32, round(16 * dpi / 96)))


def _icon_image(kind: str, color: str, size: int | None = None) -> Image.Image:
    size = size or _icon_px()
    key = (kind, color, size)
    hit = _ICON_CACHE.get(key)
    if hit is not None:
        return hit

    S = _ICON_SS
    W = size * S
    u = W / 24.0                      # 以 24×24 网格为设计基准
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = max(1, round(W * 0.075))

    def line(pts, width=lw):
        d.line([(x * u, y * u) for x, y in pts], fill=color, width=width, joint="curve")

    def poly(pts, fill=False, width=lw):
        d.polygon([(x * u, y * u) for x, y in pts], outline=color,
                  width=0 if fill else width, fill=color if fill else None)

    if kind == T_SELECT:
        # 虚线选区
        for a, b in (((4, 4), (9, 4)), ((15, 4), (20, 4)), ((4, 20), (9, 20)), ((15, 20), (20, 20)),
                     ((4, 4), (4, 9)), ((4, 15), (4, 20)), ((20, 4), (20, 9)), ((20, 15), (20, 20))):
            line([a, b])
    elif kind == T_RECT:
        line([(4, 5), (20, 5), (20, 19), (4, 19), (4, 5)])
    elif kind == T_ELLIPSE:
        d.ellipse([4 * u, 5 * u, 20 * u, 19 * u], outline=color, width=lw)
    elif kind == T_ARROW:
        line([(4, 20), (18, 6)])
        line([(11, 5.5), (18.5, 5.5), (18.5, 13)])
    elif kind == T_PEN:
        poly([(5, 19), (6.5, 13.5), (16.5, 3.5), (20.5, 7.5), (10.5, 17.5)])
        line([(14.5, 5.5), (18.5, 9.5)])
    elif kind == T_TEXT:
        f = _load_font(int(W * 0.82))
        d.text((W / 2, W / 2 + u * 0.6), "A", font=f, fill=color, anchor="mm")
    elif kind == T_SEQ:
        d.ellipse([3 * u, 3 * u, 21 * u, 21 * u], outline=color, width=lw)
        f = _load_font(int(W * 0.6))
        d.text((W / 2, W / 2 + u * 0.4), "1", font=f, fill=color, anchor="mm")
    elif kind == T_MOSAIC:
        line([(3, 3), (21, 3), (21, 21), (3, 21), (3, 3)])
        for x, y in ((6, 6), (14, 6), (6, 14), (14, 14)):
            d.rectangle([x * u, y * u, (x + 5) * u, (y + 5) * u], fill=color)
    elif kind == T_BLUR:
        # 水滴描边 + 右侧两道拖影，和其余线性图标重量一致（实心会显得过重）
        d.ellipse([7 * u, 9.5 * u, 16.5 * u, 19 * u], outline=color, width=lw)
        line([(8.6, 12), (12, 4.5), (15.4, 12)])
        line([(18.5, 11), (21.5, 11)])
        line([(18.5, 15.5), (21.5, 15.5)])
    elif kind == T_PICKER:
        line([(4, 20), (13, 11)])
        poly([(12, 10), (16.5, 3.5), (20.5, 7.5), (14, 12)])
        line([(4, 20), (7, 17)])
    elif kind == "undo":
        d.arc([5 * u, 6 * u, 19 * u, 20 * u], start=170, end=350, fill=color, width=lw)
        line([(5, 6.5), (10, 9.5), (5, 12.5)])
    elif kind == "clear":
        line([(4.5, 7), (19.5, 7)])
        line([(9.5, 7), (9.5, 4.5), (14.5, 4.5), (14.5, 7)])
        line([(7, 7), (8.4, 20), (15.6, 20), (17, 7)])
        line([(11.2, 10.5), (11.2, 16.5)])
        line([(12.8, 10.5), (12.8, 16.5)])
    elif kind == "save":
        line([(12, 3.5), (12, 14)])
        line([(8, 10), (12, 14.5), (16, 10)])
        line([(5, 17), (5, 20.5), (19, 20.5), (19, 17)])
    elif kind == "cancel":
        line([(6, 6), (18, 18)])
        line([(18, 6), (6, 18)])
    elif kind == "finish":
        line([(4.5, 12.5), (9.5, 18), (19.5, 5.5)], width=max(lw, round(W * 0.085)))
    elif kind == "width":
        line([(4, 12), (20, 12)], width=lw)
    elif kind == "width2":
        line([(4, 12), (20, 12)], width=max(2, round(W * 0.12)))
    elif kind == "width3":
        line([(4, 12), (20, 12)], width=max(3, round(W * 0.19)))
    else:
        line([(4, 4), (20, 20)])

    # 超采样画完必须降采样回目标尺寸，否则拿到的是 4 倍大的图
    img = img.resize((size, size), Image.LANCZOS)
    _ICON_CACHE[key] = img
    return img


class _Tip:
    """轻量悬停提示：深色小气泡，显示在按钮上方。"""

    def __init__(self, owner: tk.Toplevel) -> None:
        self.owner = owner
        self.win: tk.Toplevel | None = None

    def show(self, widget: tk.Widget, text: str) -> None:
        self.hide()
        if not text:
            return
        try:
            w = tk.Toplevel(self.owner)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            tk.Label(w, text=text, bg="#2c2c2e", fg="#ffffff",
                     font=("Microsoft YaHei UI", 9), padx=8, pady=4).pack()
            w.update_idletasks()
            tw, th = w.winfo_reqwidth(), w.winfo_reqheight()
            x = widget.winfo_rootx() + (widget.winfo_width() - tw) // 2
            y = widget.winfo_rooty() - th - 8
            if y < 0:
                y = widget.winfo_rooty() + widget.winfo_height() + 8
            x = max(0, min(x, self.owner.winfo_screenwidth() - tw))
            w.geometry(f"+{x}+{y}")
            self.win = w
        except tk.TclError:
            self.win = None

    def hide(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None


def _norm_box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _round_rect_pts(x0, y0, x1, y1, r) -> list[float]:
    """圆角矩形的顶点序列（用于 create_polygon(smooth=True) 或 coords 更新）。"""
    return [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0, x0 + r, y0,
    ]


def _clip_box(box, region):
    x0 = max(box[0], region[0])
    y0 = max(box[1], region[1])
    x1 = min(box[2], region[2])
    y1 = min(box[3], region[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


class ShotOverlay:
    """挂在已运行的 Tk root 上的全屏截图窗口。"""

    def __init__(
        self,
        root: tk.Tk,
        screen: Image.Image,
        origin: tuple[int, int],
        on_close: Callable[[], None],
        status_cb: Callable[[str], None] | None = None,
    ) -> None:
        self.root = root
        self.screen = screen
        self.origin = origin
        self.on_close = on_close
        self.status_cb = status_cb or (lambda s: None)

        self.win = tk.Toplevel(root)
        self.win.title("截图")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        vx, vy = origin
        self.win.geometry(f"{screen.width}x{screen.height}+{vx}+{vy}")

        self.mode = "select"
        self.tool = T_SELECT
        self.color = COLORS[0]
        self.width = 4
        self.sel: tuple[int, int, int, int] | None = None
        self.shapes: list[dict] = []
        self._seq_no = 1
        self._drag: dict | None = None
        self._handle: str | None = None
        self._img_ref: ImageTk.PhotoImage | None = None
        self._mag_ref: ImageTk.PhotoImage | None = None
        self._text_entry: tk.Entry | None = None
        self._toolbar: tk.Frame | None = None
        self._closed = False

        # 图层缓存。卡顿的根源是每收到一次 <Motion> 就把整张截图重新转成
        # PhotoImage（实测 2880×1800 ≈ 20ms）再画 4 个全屏 stipple 矩形（≈18ms），
        # 合计约 38ms/帧 ≈ 26fps。这里把「亮屏」「压暗屏」各缓存一份，
        # 选区内部只按尺寸复用裁片，拖动时只挪位置。
        self._bright_ref: ImageTk.PhotoImage | None = None
        self._dim_ref: ImageTk.PhotoImage | None = None
        self._panel_ref: ImageTk.PhotoImage | None = None
        self._panel_size: tuple[int, int] | None = None
        self._panel_geom: tuple[int, int] | None = None
        self._panel_box: tuple[int, int, int, int] | None = None
        self._panel_ts = 0.0
        self._tb_size: tuple[int, int] | None = None
        self._tb_pos: tuple[int, int] | None = None
        self._bright_name: str | None = None
        self._dim_name: str | None = None
        self._layers_key: tuple | None = None
        self._render_version = 0
        self._cursor: tuple[int, int] = (0, 0)
        self._redraw_pending = False
        self._opt_cache: dict[int, dict] = {}
        self._icon_refs: dict[tuple[str, bool], ImageTk.PhotoImage] = {}
        self._tip = _Tip(self.win)

        self.base = screen.copy()
        self.rendered = screen.copy()

        self.canvas = tk.Canvas(self.win, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.win.bind("<Escape>", lambda e: self.cancel())
        self.win.bind("<Return>", lambda e: self.finish())
        self.win.bind("<Control-z>", lambda e: self.undo())
        self.win.bind("<Control-Z>", lambda e: self.undo())
        self.win.protocol("WM_DELETE_WINDOW", self.cancel)

        self.win.after(10, self._focus)
        self._redraw()
        self.status_cb("拖动框选区域 · 双击整屏 · Esc 取消 · Enter 完成")

    # ---------- 基础 ----------

    def _focus(self) -> None:
        try:
            self.win.focus_force()
            self.win.attributes("-topmost", True)
            self.win.lift()
        except tk.TclError:
            pass

    def _to_local(self, x: int, y: int) -> tuple[int, int]:
        return int(x), int(y)

    def _icon(self, kind: str, active: bool = False) -> ImageTk.PhotoImage:
        """工具栏图标（含选中态配色），带缓存，避免每次重建。"""
        key = (kind, active)
        hit = self._icon_refs.get(key)
        if hit is None:
            color = "#ffffff" if active else "#1c1c1e"
            hit = ImageTk.PhotoImage(_icon_image(kind, color))
            self._icon_refs[key] = hit
        return hit

    def _ensure_layers(self) -> None:
        """rendered 变化时才重建「亮屏 + 压暗屏」两张缓存图。"""
        key = (self._render_version, self.rendered.size)
        if self._layers_key == key and self._bright_ref is not None:
            return
        self._bright_ref = ImageTk.PhotoImage(self.rendered)
        self._dim_ref = ImageTk.PhotoImage(self._dimmed(self.rendered))
        self._bright_name = str(self._bright_ref)
        self._dim_name = str(self._dim_ref)
        self._panel_ref = None
        self._panel_size = None
        self._panel_geom = None
        self._panel_box = None
        self._layers_key = key

    @staticmethod
    def _dimmed(img: Image.Image) -> Image.Image:
        """整屏压暗（选区外区域）。比 4 个 stipple 矩形快一个数量级。"""
        return img.point(lambda v: int(v * 0.42))

    def _panel(self, box: tuple[int, int, int, int]) -> ImageTk.PhotoImage:
        """选区内部的高亮裁片（保留给外部调用；内部走 _sync_panel）。"""
        self._sync_panel(box)
        return self._panel_ref

    def _request_redraw(self) -> None:
        """合并同一轮内的多次 <Motion>，避免重绘排队导致拖框发涩。"""
        if self._redraw_pending or self._closed:
            return
        self._redraw_pending = True
        try:
            self.win.after_idle(self._flush_redraw)
        except tk.TclError:
            self._redraw_pending = False

    def _opt(self, item: int, **kw) -> None:
        """只在选项真的变化时才调 Tk。

        对整屏底图这种大 item，重复 itemconfigure（哪怕值没变）也会引发一次
        全屏重绘（实测 ≈18ms/次），这是拖框发涩的最后一个来源。
        """
        cache = self._opt_cache.setdefault(item, {})
        changed = {k: v for k, v in kw.items() if cache.get(k) != v}
        if changed:
            cache.update(changed)
            self.canvas.itemconfigure(item, **changed)

    def _flush_redraw(self) -> None:
        self._redraw_pending = False
        self._redraw()

    def _redraw(self) -> None:
        if self._closed:
            return
        c = self.canvas
        self._ensure_layers()
        self._ensure_base()
        it = self._it
        w, h = self.rendered.size
        # 预览与放大镜是每帧重建的小对象；底图/选区框等复用同一批 item，
        # 不再 delete("all") —— 整屏图重新贴一次就要 18ms（实测）。
        c.delete("preview")
        c.delete("mag")

        if self.sel is None:
            self._opt(it["base"], image=self._dim_ref)
            for key in ("panel", "outline", "label_box", "label_txt"):
                self._opt(it[key], state="hidden")
            for hid in it["handles"]:
                self._opt(hid, state="hidden")
        else:
            x0, y0, x1, y1 = self.sel
            full = (x1 - x0) >= w - 2 and (y1 - y0) >= h - 2
            self._opt(it["base"], image=self._bright_ref if full else self._dim_ref)
            if full:
                self._opt(it["panel"], state="hidden")
            else:
                self._sync_panel((x0, y0, x1, y1), force=self._drag is None)
                c.coords(it["panel"], x0, y0)
                self._opt(it["panel"], state="normal")
            c.coords(it["outline"], x0, y0, x1, y1)
            self._opt(it["outline"], state="normal")
            # 尺寸标签（QQ 风格：选区上方）
            label = f"{x1 - x0} × {y1 - y0}"
            tw = max(76, len(label) * 9 + 18)
            lx, ly = x0, y0 - 30
            if ly < 0:
                ly = y1 + 8
            c.coords(it["label_box"], *_round_rect_pts(lx, ly, lx + tw, ly + 26, 6))
            self._opt(it["label_box"], state="normal")
            c.coords(it["label_txt"], lx + tw / 2, ly + 13)
            self._opt(it["label_txt"], text=label, state="normal")

            pts = self._handle_points() if (self.mode == "select" or self.tool == T_SELECT) else []
            for i, hid in enumerate(it["handles"]):
                if i < len(pts):
                    hx, hy = pts[i]
                    c.coords(hid, hx - HANDLE // 2, hy - HANDLE // 2,
                             hx + HANDLE // 2, hy + HANDLE // 2)
                    self._opt(hid, state="normal")
                else:
                    self._opt(hid, state="hidden")

        if self._drag and self._drag.get("preview"):
            self._draw_preview(self._drag)

        if self.mode == "select" and not self._drag:
            # 未落框时跟随光标显示放大镜 + 坐标/颜色读数
            self._draw_magnifier(self._cursor)

        self._place_toolbar()

    def _ensure_base(self) -> None:
        """底图/选区框/标签/手柄这些 item 只创建一次，之后只改属性与坐标。"""
        if getattr(self, "_it", None):
            return
        c = self.canvas
        self._it = {
            "base": c.create_image(0, 0, image=self._dim_ref, anchor="nw"),
            "panel": c.create_image(0, 0, image=self._bright_ref, anchor="nw", state="hidden"),
            "outline": c.create_rectangle(0, 0, 0, 0, outline="#00a2ff", width=2, state="hidden"),
            "label_box": self._round_rect(0, 0, 0, 0, 6, fill="#f5f5f7",
                                          outline="#d1d1d6", state="hidden"),
            "label_txt": c.create_text(0, 0, text="", fill="#1c1c1e",
                                       font=("Segoe UI", 10), state="hidden"),
            "handles": [
                c.create_oval(0, 0, 0, 0, fill="#ffffff", outline="#00a2ff",
                              width=2, state="hidden")
                for _ in range(8)
            ],
        }
        self._panel_geom = None

    def _sync_panel(self, box: tuple[int, int, int, int], force: bool = False) -> None:
        """选区内部高亮，每帧都更新（保持跟手）。

        实测代价：同尺寸换内容 0.40ms、换 image 3.19ms、只挪坐标 0.30ms —— 都远低于
        16ms 帧预算，所以不做节流；跟手优先。曾经误以为「换 image 必须整屏重绘 18ms」，
        那 18ms 实际来自「无脑给整屏底图 itemconfigure」，已由 _opt() 消除。

        台阶分配（PANEL_STEP）只为减少「换 image」的次数；台阶多出来的边角用压暗图填充，
        视觉上正好是选区外应有的样子，所以亮区边界始终精确。
        """
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0 or self._bright_name is None:
            return
        # 选区没变就不动像素（同一帧里 _redraw 可能被调两次，第二次几乎免费）
        if self._panel_box == box and not force:
            return
        sw, sh = self.rendered.size
        bw = min(sw - x0, ((w + PANEL_STEP - 1) // PANEL_STEP) * PANEL_STEP)
        bh = min(sh - y0, ((h + PANEL_STEP - 1) // PANEL_STEP) * PANEL_STEP)
        if bw <= 0 or bh <= 0:
            return

        c = self.canvas
        resized = self._panel_ref is None or self._panel_geom != (bw, bh)
        if resized:
            self._panel_ref = tk.PhotoImage(width=bw, height=bh, master=self.win)
            self._panel_geom = (bw, bh)
            c.itemconfigure(self._it["panel"], image=self._panel_ref)
        p = self._panel_ref
        try:
            # 台阶补边只在与亮区不重叠的两条带上做；尺寸没变（纯移动）时跳过 ——
            # 补边本来就是压暗的，内容略旧看不出来，但能省掉大半拷贝量。
            if resized or force:
                if bw > w:
                    p.tk.call(p, "copy", self._dim_name,
                              "-from", x0 + w, y0, x0 + bw, y0 + bh,
                              "-to", w, 0)
                if bh > h:
                    p.tk.call(p, "copy", self._dim_name,
                              "-from", x0, y0 + h, x0 + w, y0 + bh,
                              "-to", 0, h)
            p.tk.call(p, "copy", self._bright_name,
                      "-from", x0, y0, x1, y1, "-to", 0, 0)
        except tk.TclError:
            pass
        self._panel_box = box
        self._panel_ts = time.perf_counter() * 1000.0

    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        return self.canvas.create_polygon(_round_rect_pts(x0, y0, x1, y1, r), smooth=True, **kw)

    def _handle_points(self) -> list[tuple[int, int]]:
        if not self.sel:
            return []
        x0, y0, x1, y1 = self.sel
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        return [(x0, y0), (mx, y0), (x1, y0), (x1, my), (x1, y1), (mx, y1), (x0, y1), (x0, my)]

    def _handle_at(self, x: int, y: int) -> str | None:
        if not self.sel or self.tool != T_SELECT:
            return None
        names = ["nw", "n", "ne", "e", "se", "s", "sw", "w"]
        for name, (hx, hy) in zip(names, self._handle_points()):
            if abs(x - hx) <= HANDLE and abs(y - hy) <= HANDLE:
                return name
        return None

    # ---------- 放大镜 ----------

    def _draw_magnifier(self, cur: tuple[int, int]) -> None:
        cx, cy = cur
        w, h = self.screen.size
        half = MAG_SIZE // MAG_ZOOM // 2
        x0, y0 = cx - half, cy - half
        crop = self.screen.crop((x0, y0, x0 + 2 * half + 1, y0 + 2 * half + 1))
        mag = crop.resize((MAG_SIZE, MAG_SIZE), Image.NEAREST)
        draw = ImageDraw.Draw(mag)
        draw.rectangle([0, 0, MAG_SIZE - 1, MAG_SIZE - 1], outline="#ffffff", width=2)
        draw.rectangle([1, 1, MAG_SIZE - 2, MAG_SIZE - 2], outline="#000000", width=1)
        ox = (cx - x0) * MAG_ZOOM
        oy = (cy - y0) * MAG_ZOOM
        draw.line([(ox - MAG_ZOOM * half, oy), (ox + MAG_ZOOM * (half + 1), oy)], fill="#ff3b30", width=1)
        draw.line([(ox, oy - MAG_ZOOM * half), (ox, oy + MAG_ZOOM * (half + 1))], fill="#ff3b30", width=1)
        draw.rectangle([ox, oy, ox + MAG_ZOOM - 1, oy + MAG_ZOOM - 1], outline="#ff3b30", width=1)

        bar_h = 40
        canvas_img = Image.new("RGB", (MAG_SIZE, MAG_SIZE + bar_h), "#1c1c1e")
        canvas_img.paste(mag, (0, 0))
        d2 = ImageDraw.Draw(canvas_img)
        try:
            r, g, b = self.screen.getpixel((min(max(cx, 0), w - 1), min(max(cy, 0), h - 1)))
        except Exception:
            r = g = b = 0
        hexs = f"#{r:02X}{g:02X}{b:02X}"
        d2.rectangle([0, MAG_SIZE, MAG_SIZE, MAG_SIZE + bar_h], fill="#1c1c1e")
        d2.rectangle([6, MAG_SIZE + 6, 34, MAG_SIZE + 34], fill=(r, g, b), outline="#555")
        try:
            f = _load_font(14)
            d2.text((42, MAG_SIZE + 8), hexs, fill="#fff", font=f)
            d2.text((42, MAG_SIZE + 22), f"{cx},{cy}", fill="#aaa", font=f)
        except Exception:
            pass

        px, py = cx + 24, cy + 24
        if px + MAG_SIZE > w:
            px = cx - 24 - MAG_SIZE
        if py + MAG_SIZE + bar_h > h:
            py = cy - 24 - MAG_SIZE - bar_h
        if px < 0:
            px = 0
        if py < 0:
            py = 0

        self._mag_ref = ImageTk.PhotoImage(canvas_img)
        self.canvas.create_image(px, py, image=self._mag_ref, anchor="nw", tags="mag")

    # ---------- 工具栏（紧凑，对标 QQ） ----------

    def _place_toolbar(self) -> None:
        if self.sel is None or self.mode != "draw":
            if self._toolbar is not None:
                self._toolbar.place_forget()
                self._tb_pos = None
            return
        if self._toolbar is None:
            self._build_toolbar()
        tb = self._toolbar
        x0, y0, x1, y1 = self.sel
        w, h = self.rendered.size
        # update_idletasks + place 每帧都做要 3~4ms；位置没变就别动
        if self._tb_size is None:
            tb.update_idletasks()
            self._tb_size = (tb.winfo_reqwidth(), tb.winfo_reqheight())
        tw, th = self._tb_size
        # 紧凑：贴选区底部居中，越界钳制
        x = x0 + (x1 - x0 - tw) // 2
        y = y1 + 10
        if y + th > h:
            y = y0 - th - 10
        if y < 0:
            y = min(max(y1 + 10, 0), max(h - th, 0))
        if x + tw > w:
            x = max(w - tw, 8)
        if x < 8:
            x = 8
        if self._tb_pos == (x, y) and tb.winfo_ismapped():
            return
        self._tb_pos = (x, y)
        tb.place(x=x, y=y)
        tb.lift()

    def _build_toolbar(self) -> None:
        # 浅色圆角条；按钮用自绘图标，鼠标悬停出功能提示
        bar = tk.Frame(self.win, bg="#f2f2f7", padx=5, pady=5)
        self._toolbar = bar
        self._tool_btns: dict[str, tk.Button] = {}

        def bind_tip(widget: tk.Widget, text: str) -> None:
            widget.bind("<Enter>", lambda e, t=text: self._tip.show(widget, t), add="+")
            widget.bind("<Leave>", lambda e: self._tip.hide(), add="+")
            widget.bind("<ButtonPress>", lambda e: self._tip.hide(), add="+")

        def make_btn(parent, kind, cmd, tip, active=False):
            b = tk.Button(
                parent, image=self._icon(kind, active), command=cmd,
                bg="#0a84ff" if active else "#f2f2f7",
                activebackground="#d1d1d6", relief="flat", bd=0,
                highlightthickness=0, cursor="hand2", padx=4, pady=3,
            )
            b.pack(side=tk.LEFT, padx=1)
            bind_tip(b, tip)
            return b

        def sep():
            tk.Frame(bar, width=1, bg="#c7c7cc").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=4)

        # 工具组
        for tid in (T_SELECT, T_RECT, T_ELLIPSE, T_ARROW, T_PEN, T_TEXT, T_SEQ,
                    T_MOSAIC, T_BLUR, T_PICKER):
            self._tool_btns[tid] = make_btn(
                bar, tid, lambda t=tid: self._set_tool(t), TOOL_TIPS[tid],
                active=(tid == self.tool),
            )

        sep()

        # 颜色
        self._color_swatch = tk.Canvas(bar, width=18, height=18, bg=self.color,
                                       highlightthickness=1, highlightbackground="#8e8e93",
                                       cursor="hand2")
        self._color_swatch.pack(side=tk.LEFT, padx=3)
        self._color_swatch.bind("<Button-1>", lambda e: self._pick_custom_color())
        bind_tip(self._color_swatch, "自定义颜色…")
        for c in COLORS:
            s = tk.Canvas(bar, width=14, height=14, bg=c, highlightthickness=1,
                          highlightbackground="#a1a1a6", cursor="hand2")
            s.pack(side=tk.LEFT, padx=2)
            s.bind("<Button-1>", lambda e, col=c: self._set_color(col))
            bind_tip(s, f"颜色 {c.upper()}")

        sep()

        # 线宽
        for kind, wv in (("width", WIDTHS[0]), ("width2", WIDTHS[1]), ("width3", WIDTHS[2])):
            make_btn(bar, kind, lambda w=wv: self._set_width(w), f"线宽 {wv}px")

        sep()

        # 操作
        make_btn(bar, "undo", self.undo, "撤销 (Ctrl+Z)")
        make_btn(bar, "clear", self.clear, "清空所有标注")
        make_btn(bar, "save", self.save, "保存为文件…")
        make_btn(bar, "cancel", self.cancel, "取消 (Esc / 右键)")
        make_btn(bar, "finish", self.finish, "复制到剪贴板并关闭 (Enter)")

        self._highlight_tool()
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass

    def _set_tool(self, tool: str) -> None:
        if tool == T_PICKER:
            self.mode = "draw"
            self.tool = T_PICKER
            self.status_cb("取色：点击画面选择颜色")
            self._highlight_tool()
            return
        self.tool = tool
        if self.sel:
            self.mode = "draw"
            self.status_cb(self._tool_hint())
        self._highlight_tool()
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass

    def _tool_hint(self) -> str:
        return {
            T_SELECT: "拖动边缘调整选区 · Enter 完成",
            T_RECT: "拖动画矩形",
            T_ELLIPSE: "拖动画椭圆",
            T_ARROW: "拖动画箭头",
            T_PEN: "自由画笔 · 滚轮调粗细",
            T_TEXT: "点击输入文字",
            T_SEQ: "点击添加序号 ①②③",
            T_MOSAIC: "拖动打马赛克",
            T_BLUR: "拖动高斯模糊",
            T_PICKER: "点击取色",
        }.get(self.tool, "")

    def _highlight_tool(self) -> None:
        for tid, b in getattr(self, "_tool_btns", {}).items():
            active = tid == self.tool
            b.configure(
                image=self._icon(tid, active),
                bg="#0a84ff" if active else "#f2f2f7",
            )

    def _set_color(self, c: str) -> None:
        self.color = c
        if hasattr(self, "_color_swatch"):
            self._color_swatch.configure(bg=c)

    def _set_width(self, w: int) -> None:
        self.width = w

    def _pick_custom_color(self) -> None:
        c = colorchooser.askcolor(color=self.color, title="选择颜色", parent=self.win)
        if c and c[1]:
            self._set_color(c[1])

    # ---------- 鼠标 ----------

    def _on_double(self, _e) -> None:
        if self.mode == "draw" and self.sel and self.shapes:
            return
        if self.mode == "draw" and self.tool != T_SELECT:
            return
        w, h = self.screen.size
        self.sel = (0, 0, w, h)
        self.mode = "draw"
        if self.tool == T_SELECT:
            self.tool = T_RECT
            self._highlight_tool()
        self.status_cb("已选整屏 · 选择工具标注 · Enter 完成")
        self._redraw()

    def _on_right(self, e) -> None:
        self.cancel()

    def _on_wheel(self, e) -> None:
        if self.tool in (T_PEN, T_RECT, T_ELLIPSE, T_ARROW):
            if e.delta > 0:
                idx = min(WIDTHS.index(self.width) + 1 if self.width in WIDTHS else 1, len(WIDTHS) - 1)
            else:
                idx = max((WIDTHS.index(self.width) if self.width in WIDTHS else 1) - 1, 0)
            self._set_width(WIDTHS[idx])
            self.status_cb(f"线宽 {self.width}")

    def _on_press(self, e) -> None:
        x, y = self._to_local(e.x, e.y)

        if self._text_entry is not None:
            self._commit_text()

        if self.mode == "select" or self.sel is None:
            self.sel = None
            self.mode = "select"
            self._drag = {"kind": "select", "start": (x, y), "cur": (x, y), "preview": True}
            self._redraw()
            return

        if self.tool == T_PICKER:
            w, h = self.screen.size
            px, py = min(max(x, 0), w - 1), min(max(y, 0), h - 1)
            r, g, b = self.rendered.getpixel((px, py))
            self._set_color(f"#{r:02x}{g:02x}{b:02x}")
            self.tool = T_RECT
            self.status_cb(f"已取色 {self.color.upper()}")
            self._highlight_tool()
            return

        # 序号：单击即添加
        if self.tool == T_SEQ and self.sel and self._in_sel(x, y):
            size = max(18, self.width * 5)
            self.shapes.append({
                "tool": T_SEQ, "xy": (x, y), "n": self._seq_no,
                "color": self.color, "size": size,
            })
            self._seq_no += 1
            self._render()
            self.status_cb(f"序号 {self._seq_no - 1}")
            return

        hname = self._handle_at(x, y)
        if hname and self.sel:
            self._drag = {"kind": "resize", "handle": hname, "start": (x, y), "orig": self.sel}
            return

        # 点在选区外：重新框选（QQ 行为）。否则一旦进入标注态，这里就是死路 ——
        # 想重画一个框只能按 Esc 整个退出，非常不顺手。
        if self.sel is not None and not self._in_sel(x, y):
            self.sel = None
            self.mode = "select"
            self._drag = {"kind": "select", "start": (x, y), "cur": (x, y), "preview": True}
            self._redraw()
            return

        if self.tool == T_SELECT and self.sel and self._in_sel(x, y):
            self._drag = {"kind": "move", "start": (x, y), "orig": self.sel}
            return

        if self.sel and self._in_sel(x, y):
            if self.tool == T_TEXT:
                self._start_text(x, y)
                return
            self._drag = {
                "kind": "draw",
                "tool": self.tool,
                "start": (x, y),
                "cur": (x, y),
                "points": [(x, y)],
                "preview": True,
                "color": self.color,
                "width": self.width,
            }
            self._redraw()

    def _on_drag(self, e) -> None:
        if not self._drag:
            return
        x, y = self._to_local(e.x, e.y)
        kind = self._drag["kind"]
        if kind == "select":
            self._drag["cur"] = (x, y)
            sx, sy = self._drag["start"]
            self.sel = _norm_box(sx, sy, x, y)
            self._request_redraw()
        elif kind == "resize":
            self._apply_resize(x, y)
            self._request_redraw()
        elif kind == "move":
            ox0, oy0, ox1, oy1 = self._drag["orig"]
            sx, sy = self._drag["start"]
            dx, dy = x - sx, y - sy
            w, h = self.screen.size
            dx = max(dx, -ox0)
            dy = max(dy, -oy0)
            dx = min(dx, w - ox1)
            dy = min(dy, h - oy1)
            self.sel = (ox0 + dx, oy0 + dy, ox1 + dx, oy1 + dy)
            self._request_redraw()
        elif kind == "draw":
            self._drag["cur"] = (x, y)
            if self._drag["tool"] == T_PEN:
                self._drag["points"].append((x, y))
            self._request_redraw()

    def _on_release(self, e) -> None:
        if not self._drag:
            return
        x, y = self._to_local(e.x, e.y)
        d = self._drag
        self._drag = None
        kind = d["kind"]
        if kind == "select":
            if d.get("start"):
                sx, sy = d["start"]
                self.sel = _norm_box(sx, sy, x, y)
            if self.sel and (self.sel[2] - self.sel[0]) < 4 and (self.sel[3] - self.sel[1]) < 4:
                self.sel = None
                self.mode = "select"
            else:
                if self.sel:
                    x0, y0, x1, y1 = self.sel
                    if x1 - x0 < 4:
                        x1 = x0 + 4
                    if y1 - y0 < 4:
                        y1 = y0 + 4
                    w, h = self.screen.size
                    self.sel = (max(0, x0), max(0, y0), min(w, x1), min(h, y1))
                    self.mode = "draw"
                    self.status_cb("已选中区域 · 下方工具栏可标注 · Enter 完成复制")
            self._redraw()
        elif kind in ("resize", "move"):
            self._redraw()
        elif kind == "draw":
            d["cur"] = (x, y)
            if d.get("tool") == T_PEN:
                d.setdefault("points", [])
                if not d["points"] or d["points"][-1] != (x, y):
                    d["points"].append((x, y))
            self._commit_shape(d, (x, y))
            self._redraw()

    def _on_motion(self, e) -> None:
        if self._closed:
            return
        x, y = self._to_local(e.x, e.y)
        self._cursor = (x, y)
        if self.mode == "select" and not self._drag:
            # 只重画放大镜；整屏图层是静态缓存，不再每次移动都重建
            self.canvas.delete("mag")
            self._draw_magnifier(self._cursor)

    def _in_sel(self, x: int, y: int) -> bool:
        if not self.sel:
            return False
        x0, y0, x1, y1 = self.sel
        return x0 <= x <= x1 and y0 <= y <= y1

    def _apply_resize(self, x: int, y: int) -> None:
        assert self._drag and self.sel
        x0, y0, x1, y1 = self._drag["orig"]
        h = self._drag["handle"]
        if "n" in h:
            y0 = y
        if "s" in h:
            y1 = y
        if "w" in h:
            x0 = x
        if "e" in h:
            x1 = x
        self.sel = _norm_box(x0, y0, x1, y1)

    def _draw_preview(self, d: dict) -> None:
        tool = d.get("tool")
        if not tool:
            return
        x0, y0 = d["start"]
        x1, y1 = d["cur"]
        color = d.get("color", self.color)
        w = d.get("width", self.width)
        if tool in (T_RECT, T_MOSAIC, T_BLUR):
            x0, y0, x1, y1 = _norm_box(x0, y0, x1, y1)
            dash = (4, 4) if tool in (T_MOSAIC, T_BLUR) else None
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=color if tool == T_RECT else "#fff",
                                         width=w if tool == T_RECT else 2, dash=dash, tags="preview")
        elif tool == T_ELLIPSE:
            x0, y0, x1, y1 = _norm_box(x0, y0, x1, y1)
            self.canvas.create_oval(x0, y0, x1, y1, outline=color, width=w, tags="preview")
        elif tool == T_ARROW:
            self._canvas_arrow(d["start"], d["cur"], color, w)
        elif tool == T_PEN:
            pts = d.get("points") or []
            if len(pts) >= 2:
                flat = [c for p in pts for c in p]
                self.canvas.create_line(*flat, fill=color, width=w, smooth=True,
                                        capstyle=tk.ROUND, tags="preview")

    def _canvas_arrow(self, p0, p1, color, w) -> None:
        x0, y0 = p0
        x1, y1 = p1
        self.canvas.create_line(x0, y0, x1, y1, fill=color, width=w,
                                capstyle=tk.ROUND, tags="preview")
        ang = math.atan2(y1 - y0, x1 - x0)
        L = 12 + w * 2
        for da in (math.pi / 7, -math.pi / 7):
            self.canvas.create_line(
                x1, y1,
                x1 - L * math.cos(ang + da), y1 - L * math.sin(ang + da),
                fill=color, width=w, capstyle=tk.ROUND, tags="preview",
            )

    # ---------- 文本 ----------

    def _start_text(self, x: int, y: int) -> None:
        if self._text_entry:
            self._commit_text()
        size = max(14, self.width * 4)
        color = self.color
        e = tk.Entry(self.win, font=("Microsoft YaHei UI", size),
                     fg=color, bg="#ffffff", insertbackground=color, relief="solid", bd=1)
        e.place(x=x, y=y, width=240, height=max(36, size + 16))
        e.focus_set()
        e.bind("<Return>", lambda ev: self._commit_text())
        e.bind("<Escape>", lambda ev: self._cancel_text())
        e.bind("<FocusOut>", lambda ev: self._commit_text())
        self._text_entry = e
        self._text_color = color
        self._text_size = size
        self.status_cb("输入文字后回车确认")

    def _cancel_text(self) -> None:
        if self._text_entry:
            self._text_entry.destroy()
            self._text_entry = None
        self._focus()

    def _commit_text(self) -> None:
        e = self._text_entry
        if not e:
            return
        self._text_entry = None
        try:
            s = e.get().strip()
            x, y = e.winfo_x(), e.winfo_y()
            e.destroy()
        except tk.TclError:
            return
        if s and self.sel:
            size = getattr(self, "_text_size", max(14, self.width * 4))
            color = getattr(self, "_text_color", self.color)
            self.shapes.append({
                "tool": T_TEXT,
                "xy": (x, y),
                "text": s,
                "color": color,
                "size": size,
            })
            self._render()
        self._focus()

    # ---------- 形状提交 / 渲染 ----------

    def _commit_shape(self, d: dict, end: tuple[int, int]) -> None:
        tool = d.get("tool")
        if tool not in (T_RECT, T_ELLIPSE, T_ARROW, T_PEN, T_MOSAIC, T_BLUR):
            return
        x0, y0 = d["start"]
        x1, y1 = d.get("cur") or end
        if tool in (T_RECT, T_ELLIPSE, T_MOSAIC, T_BLUR):
            bx = _norm_box(int(x0), int(y0), int(x1), int(y1))
            if bx[2] - bx[0] < 2 or bx[3] - bx[1] < 2:
                return
            shape = {"tool": tool, "box": bx, "color": d.get("color", self.color),
                     "width": d.get("width", self.width)}
        elif tool == T_ARROW:
            if math.hypot(x1 - x0, y1 - y0) < 4:
                return
            shape = {"tool": tool, "p0": (x0, y0), "p1": (x1, y1),
                     "color": d.get("color", self.color), "width": d.get("width", self.width)}
        else:
            pts = list(d.get("points") or [])
            if len(pts) < 2:
                return
            shape = {"tool": tool, "points": pts, "color": d.get("color", self.color),
                     "width": d.get("width", self.width)}
        self.shapes.append(shape)
        self._render()

    def _render(self) -> None:
        img = self.base.copy()
        region = self.sel
        for s in self.shapes:
            tool = s["tool"]
            if tool in (T_MOSAIC, T_BLUR):
                box = s["box"]
                cb = _clip_box(box, region) if region else box
                if not cb:
                    continue
                x0, y0, x1, y1 = cb
                crop = img.crop(cb)
                if tool == T_MOSAIC:
                    block = max(8, s.get("width", 4) * 3)
                    cw, ch = crop.size
                    small = crop.resize((max(1, cw // block), max(1, ch // block)), Image.BILINEAR)
                    crop = small.resize((cw, ch), Image.NEAREST)
                else:
                    crop = crop.filter(ImageFilter.GaussianBlur(radius=6 + s.get("width", 4)))
                img.paste(crop, (x0, y0))
            elif tool == T_RECT:
                draw = ImageDraw.Draw(img)
                box = _clip_box(s["box"], region) if region else s["box"]
                if box:
                    draw.rectangle(box, outline=s["color"], width=s["width"])
            elif tool == T_ELLIPSE:
                draw = ImageDraw.Draw(img)
                box = _clip_box(s["box"], region) if region else s["box"]
                if box:
                    draw.ellipse(box, outline=s["color"], width=s["width"])
            elif tool == T_ARROW:
                draw = ImageDraw.Draw(img)
                x0, y0 = s["p0"]
                x1, y1 = s["p1"]
                draw.line([(x0, y0), (x1, y1)], fill=s["color"], width=s["width"])
                ang = math.atan2(y1 - y0, x1 - x0)
                L = 12 + s["width"] * 2
                for da in (math.pi / 7, -math.pi / 7):
                    draw.line(
                        [(x1, y1), (x1 - L * math.cos(ang + da), y1 - L * math.sin(ang + da))],
                        fill=s["color"], width=s["width"],
                    )
            elif tool == T_PEN:
                draw = ImageDraw.Draw(img)
                pts = s["points"]
                if region:
                    pts = [p for p in pts if region[0] <= p[0] <= region[2] and region[1] <= p[1] <= region[3]]
                if len(pts) >= 2:
                    draw.line(pts, fill=s["color"], width=s["width"], joint="curve")
            elif tool == T_TEXT:
                draw = ImageDraw.Draw(img)
                font = _load_font(s["size"])
                x, y = s["xy"]
                try:
                    draw.multiline_text((x, y), s["text"], fill=s["color"], font=font)
                except Exception:
                    draw.text((x, y), s["text"], fill=s["color"], font=font)
            elif tool == T_SEQ:
                draw = ImageDraw.Draw(img)
                x, y = s["xy"]
                r = s["size"]
                n = s["n"]
                draw.ellipse([x - r, y - r, x + r, y + r], fill=s["color"], outline="#ffffff", width=2)
                font = _load_font(max(12, int(r * 1.1)))
                tw = draw.textlength(str(n), font=font)
                th = r
                draw.text((x - tw / 2, y - th), str(n), fill="#ffffff", font=font)
        self.rendered = img
        self._render_version += 1
        self._redraw()

    def undo(self) -> None:
        if self._text_entry:
            self._commit_text()
        if not self.shapes:
            return
        removed = self.shapes.pop()
        if removed.get("tool") == T_SEQ:
            self._seq_no = max(1, self._seq_no - 1)
        self._render()
        self.status_cb("已撤销")

    def clear(self) -> None:
        if self._text_entry:
            self._cancel_text()
        self.shapes.clear()
        self._seq_no = 1
        self._render()
        self.status_cb("已清空标注")

    # ---------- 完成 / 保存 / 取消 ----------

    def _result_image(self) -> Image.Image:
        if self._text_entry:
            self._commit_text()
        self._render()
        if not self.sel:
            return self.rendered.copy()
        x0, y0, x1, y1 = self.sel
        return self.rendered.crop((x0, y0, x1, y1)).copy()

    def finish(self) -> None:
        if self._text_entry:
            self._commit_text()
        if not self.sel:
            w, h = self.screen.size
            self.sel = (0, 0, w, h)
        img = self._result_image()
        try:
            clipboard_win.copy_image(img)
            self.status_cb(f"已复制到剪贴板 {img.width}×{img.height}")
        except Exception as e:  # noqa: BLE001
            self.status_cb(f"复制失败: {e}")
        self._close()

    def save(self) -> None:
        if self._text_entry:
            self._commit_text()
        if not self.sel:
            w, h = self.screen.size
            self.sel = (0, 0, w, h)
        img = self._result_image()
        path = filedialog.asksaveasfilename(
            title="保存截图",
            defaultextension=".png",
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg;*.jpeg"),
                       ("位图", "*.bmp"), ("所有文件", "*.*")],
            initialfile="screenshot.png",
            parent=self.win,
        )
        if not path:
            return
        try:
            img.save(path)
        except OSError:
            img.save(path, "PNG")
        try:
            clipboard_win.copy_image(img)
        except Exception:
            pass
        self.status_cb(f"已保存 {path}")
        self._close()

    def cancel(self) -> None:
        self._cancel_text()
        self.status_cb("已取消截图")
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._tip.hide()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._toolbar:
                self._toolbar.destroy()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.on_close()
