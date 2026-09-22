"""系统托盘（Shell_NotifyIcon，无第三方依赖）。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import tempfile
import threading
from pathlib import Path
from typing import Callable

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# ctypes.wintypes 不提供 WNDCLASSW / WNDPROC，必须自行声明
# 返回类型必须是 LRESULT(指针宽度)，c_long 在 Windows 上是 32 位。
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,  # 返回 LRESULT（第一个参数是返回类型）
    wintypes.HWND,
    wintypes.UINT,     # UINT msg
    ctypes.c_size_t,   # WPARAM
    ctypes.c_ssize_t,  # LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_REALTIME = 0x00000010
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", wintypes.BYTE * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


# 不声明 restype 时 ctypes 一律按 32 位 int 返回，x64 上 HWND/HMODULE/HICON
# 这些 64 位句柄会被截断，随后传给别的 API 报 OverflowError。
LRESULT = ctypes.c_ssize_t
WPARAM_T = ctypes.c_size_t
LPARAM_T = ctypes.c_ssize_t

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T]

user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]

user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]

user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T]

user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]

user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
]

user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]

user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

user32.CreatePopupMenu.restype = wintypes.HMENU
user32.CreatePopupMenu.argtypes = []

user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]

user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

# TPM_RETURNCMD 时返回的是菜单项 id(UINT)，不是 BOOL
user32.TrackPopupMenu.restype = wintypes.UINT
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.LPVOID,
]

user32.DestroyMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]

user32.DestroyIcon.restype = wintypes.BOOL
user32.DestroyIcon.argtypes = [wintypes.HICON]

user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]

user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]

shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA)]


class TrayIcon:
    """托盘图标 + 右键菜单（回调在消息线程，主线程请用 after 切换）。"""

    def __init__(
        self,
        tooltip: str,
        menu_items: list[tuple[str, int, bool]] | None = None,
        on_command: Callable[[int], None] | None = None,
        on_left: Callable[[], None] | None = None,
    ) -> None:
        """
        menu_items: (标签, 命令id, 是否勾选)
        on_command(命令id)
        """
        self.tooltip = tooltip
        self.menu_items = menu_items or []
        self.on_command = on_command or (lambda cid: None)
        self.on_left = on_left or (lambda: None)
        self._nid = None
        self._hwnd = None
        self._icon = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._wndproc_ref = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3)

    def set_menu(self, items: list[tuple[str, int, bool]]) -> None:
        self.menu_items = items

    def set_tooltip(self, tip: str) -> None:
        self.tooltip = tip
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_USER + 2, 0, 0)  # 自定义刷新

    def stop(self) -> None:
        self._stop.set()
        if self._hwnd:
            user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def _run(self) -> None:
        self._wndproc_ref = WNDPROC(self._wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "SnapCtrlAltTray"
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "SnapCtrlAltTray",
            0, 0, 0, 0, 0,
            0, 0, wc.hInstance, None,
        )
        self._hwnd = hwnd
        self._icon = self._load_icon()
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._icon
        nid.szTip = self.tooltip
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._nid = nid
        self._ready.set()

        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        try:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        except Exception:
            pass
        if self._icon:
            user32.DestroyIcon(self._icon)

    def _load_icon(self):
        """从 PNG 生成 HICON，失败则用默认应用图标。"""
        try:
            from PIL import Image, ImageDraw
            import io

            img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, 29, 29], radius=8, fill=(24, 24, 27))
            d.rectangle([8, 8, 24, 22], outline=(255, 255, 255), width=2)
            d.rectangle([12, 12, 20, 18], fill=(255, 204, 0))
            # 通过临时 ICO
            # 不能写 __file__ 旁边：安装版落在 Program Files 时不可写，
            # 图标会静默退化成系统默认图标。%TEMP% 一定可写。
            ico_path = Path(tempfile.gettempdir()) / "SnapCtrlAlt_tray.ico"
            img.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32)])
            hicon = user32.LoadImageW(
                None, str(ico_path), 1, 0, 0, 0x00000010
            )
            return hicon
        except Exception:
            return user32.LoadIconW(None, 32512)  # IDI_APPLICATION

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_LBUTTONUP:
                try:
                    self.on_left()
                except Exception:
                    pass
            elif lparam == WM_RBUTTONUP:
                self._popup_menu(hwnd)
            return 0
        if msg == WM_USER + 2:
            if self._nid:
                self._nid.szTip = self.tooltip
                self._nid.uFlags = NIF_TIP | NIF_ICON | NIF_MESSAGE
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            return 0
        if msg == 0x0010:  # WM_CLOSE
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _popup_menu(self, hwnd) -> None:
        hmenu = user32.CreatePopupMenu()
        for label, cid, checked in self.menu_items:
            flags = MF_STRING | (MF_CHECKED if checked else 0)
            user32.AppendMenuW(hmenu, flags, cid, label)
        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pos.x,
            pos.y,
            0,
            hwnd,
            None,
        )
        user32.DestroyMenu(hmenu)
        if cmd:
            try:
                self.on_command(int(cmd))
            except Exception:
                pass
