"""全局热键：Ctrl+Alt+D 截图，Ctrl+Alt+Shift+Q 退出。"""

from __future__ import annotations

import ctypes
import threading
from typing import Callable

from ctypes import wintypes

user32 = ctypes.windll.user32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
VK_D = 0x44
VK_Q = 0x51

ID_SHOT = 1
ID_QUIT = 2

_HOTKEY_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_READY = threading.Event()
HOTKEY_STATUS: dict[str, bool] = {"shot": False, "quit": False}


def start_hotkeys(
    on_shot: Callable[[], None],
    on_quit: Callable[[], None],
    timeout: float = 1.5,
) -> dict[str, bool]:
    """在后台线程注册热键并泵消息；回调会在线程里执行，调用方自行切换到 UI 线程。

    返回 {"shot": bool, "quit": bool}：注册是否成功。失败必须让调用方知道 ——
    windowed 版 exe 没有 stdout，只 print 等于什么都没发生。
    """
    global _HOTKEY_THREAD
    if _HOTKEY_THREAD and _HOTKEY_THREAD.is_alive():
        return dict(HOTKEY_STATUS)
    _STOP.clear()
    _READY.clear()

    def _loop() -> None:
        # 先建立线程消息队列，否则 RegisterHotKey 可能失败
        peek = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(peek), None, 0, 0, 0)

        ok_shot = bool(user32.RegisterHotKey(None, ID_SHOT, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_D))
        if not ok_shot:
            # 已被占用时仍尝试不带 NOREPEAT
            ok_shot = bool(user32.RegisterHotKey(None, ID_SHOT, MOD_CONTROL | MOD_ALT, VK_D))
        ok_quit = bool(
            user32.RegisterHotKey(None, ID_QUIT, MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, VK_Q)
        )
        if not ok_quit:
            ok_quit = bool(user32.RegisterHotKey(None, ID_QUIT, MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_Q))

        HOTKEY_STATUS["shot"] = ok_shot
        HOTKEY_STATUS["quit"] = ok_quit
        _READY.set()
        if not ok_shot:
            print("[热键] 注册 Ctrl+Alt+D 失败，可能被其他程序占用")

        msg = wintypes.MSG()
        while not _STOP.is_set():
            # PM_REMOVE = 2；带超时以便响应停止
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            if msg.message == WM_HOTKEY:
                if msg.wParam == ID_SHOT:
                    try:
                        on_shot()
                    except Exception as e:  # noqa: BLE001
                        print(f"[热键] 截图失败: {e}")
                elif msg.wParam == ID_QUIT:
                    try:
                        on_quit()
                    except Exception as e:  # noqa: BLE001
                        print(f"[热键] 退出失败: {e}")
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, ID_SHOT)
        user32.UnregisterHotKey(None, ID_QUIT)

    _HOTKEY_THREAD = threading.Thread(target=_loop, name="hotkey", daemon=True)
    _HOTKEY_THREAD.start()
    _READY.wait(timeout)
    return dict(HOTKEY_STATUS)


def stop_hotkeys() -> None:
    _STOP.set()
    # PostQuitMessage 会杀掉整个线程消息循环
    user32.PostThreadMessageW(
        _HOTKEY_THREAD.ident if _HOTKEY_THREAD else 0, 0x0012, 0, 0  # WM_QUIT
    )
