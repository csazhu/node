"""界面设计 token 与通用绘制工具（细线、更新日志文本排版）。"""

import math
import tkinter as tk




# ================= 界面 / 设计系统 =================
# 设计 DNA：暗色「竞技数据终端」。暖调墨色中性面 + 唯一琥珀强调色，
# 用表面亮度、细分隔线与字体层级建立秩序，不用阴影/渐变/卡片套卡片。
# 色彩角色遵循 60-30-10：中性底 60%、文字与描边 30%、强调色 10%。
BG = "#0f1217"          # 页面底（带一点暖色，不用纯黑）
PANEL = "#171b22"       # 一级表面：指标区 / 表格 / 区块
PANEL_SOFT = "#1e232c"  # 二级表面：表头 / 输入框 / 斑马纹
LINE = "#2a303b"        # 描边与 1px 分隔线
TEXT = "#eef0ec"        # 主文字（暖白）
MUTED = "#9aa3ad"       # 次要文字
FAINT = "#828b96"       # 三级文字（仍满足小字 4.5:1 对比度）
ACCENT = "#e8a33d"      # 唯一强调色：关键动作、焦点、高亮数值
ACCENT_HOVER = "#f3b65c"
ACCENT_SOFT = "#3a2c17" # 强调色低饱和深底：标签 / 进度 / 辅助态
SUCCESS = "#7fb98a"
DANGER = "#e5716a"
GOLD = "#e8a33d"
# clam 主题默认把按钮 hover 背景映射成近白色 (#eeebe7)，深色界面必须整体
# 覆盖状态映射；只 style.configure 改不掉 active 状态，会变成白底白字。
BTN_HOVER = "#272d38"
BTN_PRESSED = "#333b49"
BADGE_ALERT_BG = "#2c1b1a"     # 有新版本时徽章的暗红底
BADGE_ALERT_HOVER = "#3d2523"

# 排版与间距 token：统一字体族、3 级字号、8pt 基准网格
FONT_UI = "Microsoft YaHei UI"
FONT_NUM = "Consolas"          # 数字等宽，指标与表格对齐
S1, S2, S3, S4, S5 = 4, 8, 12, 16, 24  # spacing scale


def _divider(parent, side="top", color=LINE, pad=0):
    """1px 分隔线：tkinter 没有 border-color，用无子控件的 Frame 精确模拟。"""
    line = tk.Frame(parent, bg=color, height=1 if side in ("top", "bottom") else 0,
                    width=1 if side in ("left", "right") else 0)
    line.pack(side=side, fill="y" if side in ("left", "right") else "x",
              padx=(pad, 0) if side == "left" else 0)
    return line


# ================= 更新日志 / 版本提示窗 =================
CHANGELOG_TEXT_WIDTH = 76      # 单行可容纳的半角显示宽度（中文按 2 计）
CHANGELOG_MAX_LINES = 16       # 超过则固定高度并启用滚动条


def _display_width(text):
    return sum(2 if ord(c) > 127 else 1 for c in str(text))


def _changelog_lines(entries):
    """结构化行：('version', 版本号, 日期) / ('item', 说明) / ('blank', '')。"""
    rows = []
    for e in entries or []:
        rows.append(("version", f"v{e.get('version', '?')}", e.get("date") or ""))
        for item in e.get("items") or []:
            rows.append(("item", item))
        rows.append(("blank", ""))
    return rows or [("item", "暂无更新内容")]


def _changelog_metrics(entries):
    """按内容估算 Text 高度（行数）与是否需要滚动条，避免固定 460px 大空白。"""
    lines = 0
    for row in _changelog_lines(entries):
        lines += (max(1, math.ceil(_display_width(row[1]) / CHANGELOG_TEXT_WIDTH))
                  if row[0] == "item" else 1)
    return max(5, min(lines, CHANGELOG_MAX_LINES)), lines > CHANGELOG_MAX_LINES


def _render_changelog(text, entries):
    """版本行高亮、条目悬挂缩进，避免用空格模拟列表造成的断行错位。"""
    text.configure(state="normal")
    text.delete("1.0", "end")
    for row in _changelog_lines(entries):
        kind, value = row[0], row[1]
        if kind == "version":
            text.insert("end", value, "version")
            if len(row) > 2 and row[2]:
                text.insert("end", "    " + row[2], "date")
            text.insert("end", "\n")
        elif kind == "item":
            text.insert("end", "•  ", ("item", "bullet"))
            text.insert("end", value + "\n", "item")
        else:
            text.insert("end", "\n", "blank")
    text.configure(state="disabled")
