# -*- mode: python ; coding: utf-8 -*-
# SnapCtrlAlt 免安装单文件 spec
#
# 用法（在仓库根目录执行）：
#   python -m PyInstaller packaging\SnapCtrlAlt-portable.spec
#
# 排除项已核对过工程的全部 import（只用 ctypes / io / PIL / math / tkinter / typing /
# threading / re / subprocess / json / os / sys / winreg / pathlib / argparse / queue）。
# numpy 不是本工程依赖，是 PyInstaller 从 site-packages 顺带拖进来的，排除后体积约减 40%。

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # 仓库根目录

a = Analysis(
    [os.path.join(ROOT, 'snap.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'setuptools', 'pip', 'pydoc', 'doctest', 'unittest', 'xmlrpc',
        'email', 'http', 'urllib', 'webbrowser', 'multiprocessing', 'sqlite3',
        'lib2to3', 'distutils', 'pdb', 'tkinter.test', 'test',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SnapCtrlAlt-portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(SPECPATH, 'SnapCtrlAlt.ico')],
)
