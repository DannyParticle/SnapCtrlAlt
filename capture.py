"""屏幕截图与虚拟屏度量（Windows）。"""

from __future__ import annotations

import ctypes

from PIL import Image, ImageGrab


def enable_dpi_awareness() -> None:
    """必须在创建 Tk 之前调用，保证坐标与物理像素一致。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """返回虚拟屏 (x, y, w, h)。"""
    user32 = ctypes.windll.user32
    x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    w = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    h = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    return int(x), int(y), int(w), int(h)


def grab_full_screen() -> Image.Image:
    """截取整块虚拟屏，返回 RGB 图。"""
    return ImageGrab.grab(all_screens=True, include_layered_windows=True).convert("RGB")
