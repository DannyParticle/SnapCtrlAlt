"""应用设置：JSON 配置 + 开机自启。"""

from __future__ import annotations

import json
import os
import sys
import winreg
from pathlib import Path

APP_NAME = "SnapCtrlAlt"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def app_dir() -> Path:
    """可写数据目录（便携版放 exe 旁，安装版放 %APPDATA%）。"""
    if getattr(sys, "frozen", False):
        # 安装到 Program Files 时不可写 → 用 AppData
        exe = Path(sys.executable)
        if not os.access(exe.parent, os.W_OK):
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            d = base / APP_NAME
        else:
            d = exe.parent
    else:
        d = Path(__file__).resolve().parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_dir() / "config.json"


DEFAULTS = {
    "hotkey": "ctrl+alt+d",
    "prefer_qq": True,
    "qq_hotkey": "ctrl+alt+a",
    "autostart": False,
    "save_dir": "",
}


def load_settings() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save_settings(cfg: dict) -> None:
    p = config_path()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enabled:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_cmd())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError as e:
        raise RuntimeError(f"写入开机自启失败: {e}") from e


def _launch_cmd() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = Path(__file__).resolve().parent / "snap.py"
    py = sys.executable
    return f'"{py}" "{script}"'
