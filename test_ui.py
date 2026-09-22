"""界面自动化：模拟框选 → 矩形标注 → 完成复制。"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, r"C:\Users\李自远\XiaomiMiMoProjects/2026-09-22/ctrl-alt")

import capture

capture.enable_dpi_awareness()

import tkinter as tk

import clipboard_win
from overlay import ShotOverlay, T_RECT
from capture import grab_full_screen, virtual_screen_bounds


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    img = grab_full_screen()
    origin = virtual_screen_bounds()[:2]
    closed = {"v": False}
    status: list[str] = []

    ov = ShotOverlay(root, img, origin, on_close=lambda: closed.__setitem__("v", True),
                     status_cb=status.append)

    def pump(n: int = 5) -> None:
        for _ in range(n):
            root.update()

    pump()

    # 1) 框选 (200,200) -> (800,600)
    c = ov.canvas
    c.event_generate("<ButtonPress-1>", x=200, y=200)
    c.event_generate("<B1-Motion>", x=500, y=400)
    c.event_generate("<B1-Motion>", x=800, y=600)
    c.event_generate("<ButtonRelease-1>", x=800, y=600)
    pump()
    assert ov.sel == (200, 200, 800, 600), f"sel={ov.sel}"
    assert ov.mode == "draw", ov.mode
    print("框选 OK", ov.sel)

    # 2) 工具栏已创建
    assert ov._toolbar is not None
    print("工具栏 OK")

    # 3) 矩形标注
    ov._set_tool(T_RECT)
    c.event_generate("<ButtonPress-1>", x=250, y=250)
    c.event_generate("<B1-Motion>", x=400, y=350)
    c.event_generate("<ButtonRelease-1>", x=400, y=350)
    pump()
    assert len(ov.shapes) == 1, ov.shapes
    assert ov.shapes[0]["tool"] == T_RECT
    print("矩形标注 OK", ov.shapes[0]["box"])

    # 4) 撤销 / 重画（坐标错开，避免触发 Tk 双击）
    ov.undo()
    pump()
    assert len(ov.shapes) == 0
    c.event_generate("<ButtonPress-1>", x=260, y=260)
    c.event_generate("<B1-Motion>", x=390, y=370)
    c.event_generate("<ButtonRelease-1>", x=510, y=410)
    pump()
    assert len(ov.shapes) == 1, ov.shapes
    print("撤销/重画 OK", ov.shapes[0]["box"])

    # 5) 画笔
    from overlay import T_PEN

    ov._set_tool(T_PEN)
    c.event_generate("<ButtonPress-1>", x=300, y=300)
    for i in range(10):
        c.event_generate("<B1-Motion>", x=300 + i * 15, y=300 + i * 8)
    c.event_generate("<ButtonRelease-1>", x=435, y=372)
    pump()
    assert len(ov.shapes) == 2, ov.shapes
    print("画笔 OK")

    # 6) 马赛克
    from overlay import T_MOSAIC

    ov._set_tool(T_MOSAIC)
    c.event_generate("<ButtonPress-1>", x=600, y=400)
    c.event_generate("<B1-Motion>", x=750, y=550)
    c.event_generate("<ButtonRelease-1>", x=750, y=550)
    pump()
    assert len(ov.shapes) == 3, ov.shapes
    print("马赛克 OK")

    # 7) 取色
    from overlay import T_PICKER

    ov._set_tool(T_PICKER)
    c.event_generate("<ButtonPress-1>", x=400, y=400)
    pump()
    assert ov.color.startswith("#") and len(ov.color) == 7
    print("取色 OK", ov.color)

    # 8) 完成 → 剪贴板 + 关闭
    # 先确认选区仍在
    assert ov.sel == (200, 200, 800, 600)
    result = ov._result_image()
    assert result.size == (600, 400), result.size
    clipboard_win.copy_image(result)
    ov.finish()
    pump()
    assert closed["v"]
    print("完成复制 OK", result.size)

    root.destroy()
    print("界面自测全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
