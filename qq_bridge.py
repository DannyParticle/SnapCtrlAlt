"""检测 QQ/TIM 并尝试唤起其截图。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import re
import subprocess
import time
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1


# INPUT 在 x64 上是 40 字节：联合体必须包含 MOUSEINPUT（最大的成员）。
# 只声明 KEYBDINPUT 会得到 sizeof(INPUT)=32，SendInput 因 cbSize 不匹配
# 直接返回 0 —— 按键一个都发不出去，而且不报错。
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    _anonymous_ = ("i",)
    _fields_ = [("type", wintypes.DWORD), ("i", _I)]


user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

VK = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "menu": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

QQ_PROCESS_NAMES = {"qq.exe", "tim.exe", "weixin.exe", "wechat.exe"}


def _parse_hotkey(spec: str) -> list[int]:
    """'ctrl+alt+a' → [VK_CTRL, VK_ALT, VK_A]。"""
    parts = [p.strip().lower() for p in re.split(r"[+]", spec or "") if p.strip()]
    keys: list[int] = []
    for p in parts:
        if p not in VK:
            raise ValueError(f"未知按键: {p}")
        keys.append(VK[p])
    return keys


def _send_keys(keys: list[int]) -> int:
    """SendInput 依次按下、再逆序抬起。返回真正被注入的事件数。"""
    arr = (INPUT * (len(keys) * 2))()
    i = 0
    for k in keys:
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki.wVk = k
        arr[i].ki.dwFlags = 0
        i += 1
    for k in reversed(keys):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki.wVk = k
        arr[i].ki.dwFlags = KEYEVENTF_KEYUP
        i += 1
    return int(user32.SendInput(len(arr), arr, ctypes.sizeof(INPUT)))


def qq_pids() -> set[int]:
    """QQ / TIM / 微信 的进程 id 集合。"""
    pids: set[int] = set()
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=0x08000000,
            timeout=2,
            text=True,
            errors="replace",
        )
    except (subprocess.SubprocessError, OSError):
        return pids
    for line in out.splitlines():
        cols = [c.strip('"') for c in line.split('","')]
        if len(cols) >= 2 and cols[0].lower() in QQ_PROCESS_NAMES:
            try:
                pids.add(int(cols[1]))
            except ValueError:
                pass
    return pids


def qq_running() -> bool:
    """是否有 QQ / TIM / 微信进程。"""
    return bool(qq_pids())


def foreground_pid() -> int:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def wait_for_qq_foreground(pids: set[int], timeout_ms: int = 900) -> bool:
    """QQ 截图界面弹出时会抢到前台；前台进程变成 QQ 即认为唤起成功。"""
    if not pids:
        return False
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if foreground_pid() in pids:
            return True
        time.sleep(0.06)
    return False


def try_invoke_qq_screenshot(qq_hotkey: str = "ctrl+alt+a") -> bool:
    """发送 QQ 截图热键。只有事件真的注入成功才返回 True。"""
    try:
        keys = _parse_hotkey(qq_hotkey)
    except ValueError:
        keys = _parse_hotkey("ctrl+alt+a")
    return _send_keys(keys) == len(keys) * 2


def route_screenshot(
    prefer_qq: bool,
    qq_hotkey: str,
    open_local: Callable[[], None],
    status: Callable[[str], None] | None = None,
) -> None:
    """
    分流：QQ 运行且 prefer_qq → 先试 QQ 截图；确认 QQ 真的接管了才返回，
    否则回落到本地截图。

    静默失败是这里最大的坑：热键发出去了、QQ 却没弹（例如 QQ 那侧没绑定该快捷键），
    用户会觉得「按了没反应」。所以每一层失败都要有兜底。
    """
    status = status or (lambda s: None)
    if not prefer_qq:
        open_local()
        return
    pids = qq_pids()
    if not pids:
        open_local()
        return
    status(f"检测到 QQ/TIM，发送截图键 {qq_hotkey}")
    try:
        injected = try_invoke_qq_screenshot(qq_hotkey)
    except Exception as e:  # noqa: BLE001
        status(f"唤起 QQ 截图失败: {e}，改用本地截图")
        open_local()
        return
    if not injected:
        status("QQ 截图键注入失败，改用本地截图")
        open_local()
        return
    if wait_for_qq_foreground(pids):
        return
    status("QQ 未接管截图（可能未绑定该快捷键），改用本地截图")
    open_local()
