# SnapCtrlAlt 1.1.1

Windows 截图小工具首个公开版本。`Ctrl+Alt+D` 全局唤起，交互对标 QQ 截图；QQ / TIM 开着时优先走 QQ 截图，否则用本地覆盖层。

作者：mimo、DeepSeek Harness 与 DannyParticle。许可：[MIT](LICENSE)。

## 下载

| 资产 | 用途 |
|------|------|
| `SnapCtrlAlt-portable.exe` | 免安装，双击即用（推荐先试这个） |
| `SnapCtrlAlt-Setup-1.1.1.exe` | 安装版，免 UAC；可选开机自启 |
| `SnapCtrlAlt-selftest.exe` | 控制台诊断版，加 `--selftest` 自检 |

系统要求：Windows 10 / 11（x64）。从源码跑另需 Python 3.12+ 与 Pillow。

## 上手

1. 双击 `SnapCtrlAlt-portable.exe`，托盘出现图标。
2. 按 `Ctrl+Alt+D` 框选截图，`Enter` 复制进剪贴板。
3. 退出：托盘菜单，或 `Ctrl+Alt+Shift+Q`。

框选手柄改大小、框内拖动平移、双击选整屏。标注支持矩形、椭圆、箭头、画笔、文字、马赛克、高斯模糊、取色。

配置写在 `config.json`（便携版在 exe 旁，安装版在 `%APPDATA%\SnapCtrlAlt\`），可改热键、QQ 分流、保存目录。

## 这一版做了什么

**1.1.1**（当前）

- 修：拖动、调整选区时阴影滞后。去掉误加的 90 ms 节流，改为每帧精确更新。
- 修：整屏底图在值未变时仍触发全屏重绘（约 18 ms/帧）。
- 优：标注态下在选区外按下可直接重新框选。
- 本机 40 帧实测：创建 2.7 ms / 调整 11.1 ms / 移动 6.6 ms / 标注 4.2 ms，均低于 16 ms。

**1.1.0**

- 工具栏图标改为自绘线性图标，悬停出中文提示。
- 拖框帧耗时从约 38 ms 降到约 1–3 ms。

**1.0.0**

- 全局热键、托盘常驻、开机自启、QQ 分流、免安装与安装版打包。
- 热键注册失败改为可见提示。

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 已知问题

- 高速拖动选区时偶见轻微拖影，不影响使用。
- 热键被其它程序占用时会弹窗提示，需先释放冲突热键。

## 校验

- 诊断版 `SnapCtrlAlt-selftest.exe --selftest`：截图、剪贴板、配置等 7 项检查全过，退出码 0。
- 免安装版（onefile）与安装版载荷（onedir）均实跑过：托盘窗口可被 `FindWindowW("SnapCtrlAltTray")` 找到，退出后无残留进程。
