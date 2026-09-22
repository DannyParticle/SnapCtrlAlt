#!/usr/bin/env python3
"""Ctrl+Alt+D 截图小工具（托盘常驻 + QQ 分流）。

- QQ/TIM 运行时优先调用 QQ 截图；否则用本地截图
- 托盘菜单：立即截图 / 开机自启 / 优先QQ截图 / 设置 / 退出
- 全局热键 Ctrl+Alt+D 截图，Ctrl+Alt+Shift+Q 退出
"""

from __future__ import annotations

import argparse
import queue
import sys
from pathlib import Path

from capture import enable_dpi_awareness, grab_full_screen, virtual_screen_bounds

enable_dpi_awareness()

import hotkey  # noqa: E402
import qq_bridge  # noqa: E402
import settings as app_settings  # noqa: E402
from overlay import ShotOverlay  # noqa: E402

# 托盘菜单命令 id
CMD_SHOT = 101
CMD_AUTOSTART = 102
CMD_PREFER_QQ = 103
CMD_SETTINGS = 104
CMD_TEST_QQ = 105
CMD_QUIT = 109


class App:
    def __init__(self) -> None:
        import tkinter as tk

        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("SnapCtrlAlt")
        self.cfg = app_settings.load_settings()
        self._overlay: ShotOverlay | None = None
        self._q: queue.Queue[str] = queue.Queue()
        self._tray = None
        self._panel = None
        self.root.after(50, self._poll)

    # ---------- 托盘 ----------

    def _tray_menu(self) -> list[tuple[str, int, bool]]:
        return [
            ("立即截图", CMD_SHOT, False),
            ("开机自启", CMD_AUTOSTART, bool(self.cfg.get("autostart"))),
            ("优先调用 QQ 截图", CMD_PREFER_QQ, bool(self.cfg.get("prefer_qq"))),
            ("测试 QQ 截图", CMD_TEST_QQ, False),
            ("设置…", CMD_SETTINGS, False),
            ("退出", CMD_QUIT, False),
        ]

    def _start_tray(self) -> None:
        from tray import TrayIcon

        self._tray = TrayIcon(
            tooltip="截图工具 Ctrl+Alt+D",
            menu_items=self._tray_menu(),
            on_command=lambda cid: self._q.put(f"cmd:{cid}"),
            on_left=lambda: self._q.put("shot"),
        )
        self._tray.start()

    def _refresh_tray(self) -> None:
        if self._tray:
            self._tray.set_menu(self._tray_menu())

    def _on_tray_cmd(self, cid: int) -> None:
        if cid == CMD_SHOT:
            self.trigger_shot()
        elif cid == CMD_AUTOSTART:
            self.cfg["autostart"] = not self.cfg.get("autostart")
            try:
                app_settings.set_autostart(self.cfg["autostart"])
            except RuntimeError as e:
                self._status(str(e))
            app_settings.save_settings(self.cfg)
            self._refresh_tray()
            self._status(f"开机自启已{'开启' if self.cfg['autostart'] else '关闭'}")
        elif cid == CMD_PREFER_QQ:
            self.cfg["prefer_qq"] = not self.cfg.get("prefer_qq")
            app_settings.save_settings(self.cfg)
            self._refresh_tray()
            self._status(f"优先 QQ 截图已{'开启' if self.cfg['prefer_qq'] else '关闭'}")
        elif cid == CMD_TEST_QQ:
            self.cfg["prefer_qq"] = True
            self.trigger_shot()
        elif cid == CMD_SETTINGS:
            self._q.put("settings")
        elif cid == CMD_QUIT:
            self._q.put("quit")

    # ---------- 设置面板 ----------

    def show_settings(self) -> None:
        import tkinter as tk
        from tkinter import ttk, filedialog

        if self._panel is not None:
            try:
                if self._panel.winfo_exists():
                    self._panel.deiconify()
                    self._panel.lift()
                    return
            except tk.TclError:
                pass

        panel = tk.Toplevel(self.root)
        panel.title("截图工具 设置")
        panel.geometry("360x320+80+80")
        panel.resizable(False, False)
        panel.attributes("-topmost", True)
        self._panel = panel

        frm = tk.Frame(panel, padx=16, pady=14)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(frm, text="SnapCtrlAlt 截图工具",
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        tk.Label(frm, text="截图 Ctrl+Alt+D　　退出 Ctrl+Alt+Shift+Q",
                 fg="#666").pack(anchor="w", pady=(6, 12))

        # 自启
        self._var_autostart = tk.BooleanVar(value=bool(self.cfg.get("autostart")))
        tk.Checkbutton(frm, text="开机自启", variable=self._var_autostart,
                       command=self._apply_autostart).pack(anchor="w")

        # QQ
        self._var_prefer_qq = tk.BooleanVar(value=bool(self.cfg.get("prefer_qq")))
        tk.Checkbutton(frm, text="QQ/TIM 运行时优先调用 QQ 截图",
                       variable=self._var_prefer_qq,
                       command=self._apply_prefer_qq).pack(anchor="w")

        # QQ 热键
        row = tk.Frame(frm)
        row.pack(fill=tk.X, pady=(10, 0))
        tk.Label(row, text="QQ 截图键").pack(side=tk.LEFT)
        self._ent_qq = tk.Entry(row, width=16)
        self._ent_qq.insert(0, str(self.cfg.get("qq_hotkey", "ctrl+alt+a")))
        self._ent_qq.pack(side=tk.LEFT, padx=8)

        row2 = tk.Frame(frm)
        row2.pack(fill=tk.X, pady=(10, 0))
        tk.Label(row2, text="保存目录").pack(side=tk.LEFT)
        self._ent_dir = tk.Entry(row2, width=22)
        self._ent_dir.insert(0, str(self.cfg.get("save_dir", "")))
        self._ent_dir.pack(side=tk.LEFT, padx=8)
        tk.Button(row2, text="…", width=3,
                  command=lambda: self._browse_dir()).pack(side=tk.LEFT)

        tk.Label(frm, text="说明：QQ 打开时按快捷键会调用 QQ 截图（默认 Ctrl+Alt+A）。\n"
                           "若 QQ 截图键已改，请同步修改上面的「QQ 截图键」。\n"
                           "托盘图标右键可快速开关自启与 QQ 优先。",
                 fg="#888", justify="left").pack(anchor="w", pady=(14, 0))

        btns = tk.Frame(frm)
        btns.pack(side=tk.BOTTOM, fill=tk.X, pady=(12, 0))
        tk.Button(btns, text="立即截图", command=self.trigger_shot).pack(side=tk.LEFT)
        tk.Button(btns, text="保存设置", command=self._save_from_panel).pack(side=tk.LEFT, padx=8)
        tk.Button(btns, text="退出", command=self.quit).pack(side=tk.RIGHT)

    def _browse_dir(self) -> None:
        from tkinter import filedialog

        d = filedialog.askdirectory(title="选择截图默认保存目录")
        if d:
            self._ent_dir.delete(0, "end")
            self._ent_dir.insert(0, d)

    def _apply_autostart(self) -> None:
        v = self._var_autostart.get()
        self.cfg["autostart"] = v
        try:
            app_settings.set_autostart(v)
            self._status(f"开机自启已{'开启' if v else '关闭'}")
        except RuntimeError as e:
            self._status(str(e))
        app_settings.save_settings(self.cfg)
        self._refresh_tray()

    def _apply_prefer_qq(self) -> None:
        self.cfg["prefer_qq"] = self._var_prefer_qq.get()
        app_settings.save_settings(self.cfg)
        self._refresh_tray()

    def _save_from_panel(self) -> None:
        self.cfg["qq_hotkey"] = self._ent_qq.get().strip() or "ctrl+alt+a"
        self.cfg["save_dir"] = self._ent_dir.get().strip()
        self.cfg["autostart"] = self._var_autostart.get()
        self.cfg["prefer_qq"] = self._var_prefer_qq.get()
        try:
            app_settings.set_autostart(self.cfg["autostart"])
        except RuntimeError as e:
            self._status(str(e))
        app_settings.save_settings(self.cfg)
        self._refresh_tray()
        self._status("设置已保存")

    # ---------- 触发截图 ----------

    def trigger_shot(self) -> None:
        self._q.put("shot")

    def quit(self) -> None:
        self._q.put("quit")

    def _poll(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if msg == "shot":
                    self._start_shot()
                elif msg == "quit":
                    self._do_quit()
                    return
                elif msg == "settings":
                    self.show_settings()
                elif msg.startswith("cmd:"):
                    self._on_tray_cmd(int(msg.split(":", 1)[1]))
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(50, self._poll)
        except self.tk.TclError:
            pass

    def _start_shot(self) -> None:
        if self._overlay and not self._overlay._closed:
            try:
                self._overlay.win.lift()
            except self.tk.TclError:
                pass
            return
        # 隐藏设置面板，避免截进去
        try:
            if self._panel and self._panel.winfo_exists():
                self._panel.withdraw()
        except Exception:
            pass
        self.root.update_idletasks()
        self.root.after(150, self._do_shot)

    def _do_shot(self) -> None:
        # 先抓屏：如果 QQ 没接管而回落到本地，用的应该是按下热键那一刻的画面，
        # 而不是等 QQ 探测超时（约 0.9s）之后才抓。
        try:
            img = grab_full_screen()
            origin = virtual_screen_bounds()[:2]
        except Exception as e:  # noqa: BLE001
            self._status(f"截图失败: {e}")
            return
        qq_bridge.route_screenshot(
            prefer_qq=bool(self.cfg.get("prefer_qq", True)),
            qq_hotkey=str(self.cfg.get("qq_hotkey", "ctrl+alt+a")),
            open_local=lambda: self._open_local(img, origin),
            status=self._status,
        )

    def _open_local(self, img=None, origin=None) -> None:
        try:
            if img is None:
                img = grab_full_screen()
            if origin is None:
                origin = virtual_screen_bounds()[:2]
            self._overlay = ShotOverlay(
                self.root,
                img,
                origin,
                on_close=self._on_overlay_close,
                status_cb=self._status,
            )
        except Exception as e:  # noqa: BLE001
            self._status(f"截图失败: {e}")
            try:
                if self._panel and self._panel.winfo_exists():
                    self._panel.deiconify()
            except Exception:
                pass

    def _on_overlay_close(self) -> None:
        self._overlay = None
        try:
            if self._panel and self._panel.winfo_exists():
                self._panel.deiconify()
        except Exception:
            pass

    def _status(self, text: str) -> None:
        print(f"[状态] {text}", flush=True)

    def _do_quit(self) -> None:
        if self._overlay and not self._overlay._closed:
            try:
                self._overlay.win.destroy()
                self._overlay._closed = True
            except Exception:
                pass
            self._overlay = None
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
        hotkey.stop_hotkeys()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self._start_tray()
        # 若配置了开机自启且与注册表不一致，以注册表为准
        if app_settings.autostart_enabled() != bool(self.cfg.get("autostart")):
            self.cfg["autostart"] = app_settings.autostart_enabled()
            app_settings.save_settings(self.cfg)
        hotkey_status = hotkey.start_hotkeys(
            on_shot=lambda: self._q.put("shot"),
            on_quit=lambda: self._q.put("quit"),
        )
        if hotkey_status.get("shot"):
            self._status("已在托盘运行：Ctrl+Alt+D 截图，Ctrl+Alt+Shift+Q 退出")
        else:
            # windowed 版 exe 没有 stdout，热键失败必须让用户看见，否则就是「按了没反应」
            self._status("Ctrl+Alt+D 注册失败：可能被其他程序占用；可用托盘菜单「立即截图」")
            self.root.after(200, self._warn_hotkey_conflict)
        self.root.mainloop()

    def _warn_hotkey_conflict(self) -> None:
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                "截图工具",
                "全局热键 Ctrl+Alt+D 注册失败，可能已被其他程序占用（例如 QQ）。\n\n"
                "你仍然可以用托盘菜单里的「立即截图」。",
            )
        except Exception:  # noqa: BLE001
            pass


def selftest() -> int:
    from PIL import Image, ImageDraw

    print("1. 抓屏…")
    img = grab_full_screen()
    print(f"   OK {img.size}")

    print("2. 标注渲染…")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 200, 120], outline="#ff3b30", width=4)
    crop = img.crop((0, 0, 400, 300))
    assert crop.size == (400, 300)

    print("3. 马赛克…")
    block = 12
    c = crop.copy()
    small = c.resize((max(1, 400 // block), max(1, 300 // block)))
    small.resize((400, 300), Image.NEAREST)

    print("4. 剪贴板…")
    import clipboard_win

    clipboard_win.copy_image(crop)
    clipboard_win.copy_text("snap test")

    print("5. 设置读写…")
    cfg = app_settings.load_settings()
    assert "prefer_qq" in cfg and "autostart" in cfg
    print("   OK", list(cfg))

    print("6. QQ 分流模块…")
    import qq_bridge

    _ = qq_bridge.qq_running()
    _ = qq_bridge._parse_hotkey("ctrl+alt+a")

    print("7. Tk…")
    import tkinter as tk

    r = tk.Tk()
    r.withdraw()
    r.destroy()

    print("全部通过")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ctrl+Alt+D 截图小工具")
    p.add_argument("--selftest", action="store_true", help="运行自检")
    p.add_argument("--once", action="store_true", help="立即打开一次本地截图界面")
    p.add_argument("--settings", action="store_true", help="打开设置面板")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.once:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        img = grab_full_screen()
        origin = virtual_screen_bounds()[:2]
        ShotOverlay(root, img, origin, on_close=root.destroy, status_cb=print)
        root.mainloop()
        return 0

    app = App()
    if args.settings:
        app.root.after(100, app.show_settings)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
