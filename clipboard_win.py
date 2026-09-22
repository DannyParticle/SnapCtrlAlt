"""把图像写入 Windows 剪贴板（CF_DIB + CF_PNG）。"""

from __future__ import annotations

import ctypes
import io
import ctypes.wintypes as wintypes

from PIL import Image

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_DIB = 8
GHND = 0x0042
CF_UNICODETEXT = 13

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


def _put(fmt: int, data: bytes) -> None:
    handle = kernel32.GlobalAlloc(GHND, len(data))
    if not handle:
        raise MemoryError("GlobalAlloc failed")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise MemoryError("GlobalLock failed")
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)
        raise ctypes.WinError()


def _bmp_dib_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    # 去掉 14 字节 BITMAPFILEHEADER，剪贴板要的是裸 DIB
    return buf.getvalue()[14:]


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def copy_image(img: Image.Image) -> None:
    """复制图像到系统剪贴板。"""
    if not user32.OpenClipboard(None):
        raise ctypes.WinError()
    try:
        user32.EmptyClipboard()
        _put(CF_DIB, _bmp_dib_bytes(img))
        png_fmt = user32.RegisterClipboardFormatW("PNG")
        if png_fmt:
            try:
                _put(png_fmt, _png_bytes(img))
            except OSError:
                pass
    finally:
        user32.CloseClipboard()


def copy_text(text: str) -> None:
    if not user32.OpenClipboard(None):
        raise ctypes.WinError()
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        _put(CF_UNICODETEXT, data)
    finally:
        user32.CloseClipboard()
