"""配置常量、内置更新日志与本地 JSON 读取（无 UI 依赖）。"""

import json
import os
import sys


APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

FIREBASE_API_KEY = "AIzaSyCKOLF7HtJf-JLF4rU7i8gxk-dZvWgPEfw"
API_BASE = "https://windy10v10ai.com"
TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

# ================= 自动刷新 / 取数重试口径 =================
# 只有勾上「自动刷新」才启用：一轮刷新「完成后」再等 5 秒发起下一轮，保证请求不堆叠。
AUTO_REFRESH_INTERVAL_MS = 5000
# 自动刷新开关状态存进本地库的 sync_meta：用户勾/取消时即时落盘，重启 exe 沿用上次选择。
PREF_AUTO_REFRESH = "pref_auto_refresh"
# 每个接口各起独立线程，取到成功数据即止；失败最多尝试 5 次，每次失败后间隔 0.5 秒。
# config.json 可用 fetchMaxAttempts / fetchRetryIntervalMs（毫秒）覆盖。
FETCH_MAX_ATTEMPTS = 5
FETCH_RETRY_INTERVAL_S = 0.5
FETCH_SPIN_MS = 120          # 手动刷新时按钮旋转动画的帧间隔
# 单轮 = 1 次 Firebase token 刷新 + 3 个业务接口（各走独立线程并行）。业务接口正常 <1s，
# 给 5s 容忍抖动；token 端点走境外代理，给 10s。失败由线程内重试兜住，不再靠下一轮。
API_TIMEOUT = 5.0
TOKEN_TIMEOUT = 10.0
# Firebase id_token 有效期 1 小时，提前 10 分钟过期，避免每 5 秒刷一次 token。
TOKEN_CACHE_TTL = 3000

# ================= 版本与更新 =================
APP_VERSION = "1.1.8"
# 服务器版本清单：只维护 GitHub main 分支根目录的 version.json，改它即代表发新版；
# 该文件不随 exe 打包，客户端启动时联网读取，失败静默跳过。
VERSION_URL = "https://raw.githubusercontent.com/csazhu/node/main/version.json"
VERSION_TIMEOUT = 10.0         # 子线程检查，不阻塞启动；冷启动首请求实测约 5.2s
# 自动刷新每轮静默顺带查一次版本；最小间隔 5 分钟，避免每 5 秒轮询 GitHub。
VERSION_CHECK_MIN_INTERVAL_MS = 5 * 60 * 1000
DOWNLOAD_TIMEOUT = 60.0        # exe 较大；urllib 的 timeout 是单次 socket 操作超时
UPDATE_EXE_NAME = "dota-stats.exe"
UPDATE_NEW_NAME = "dota-stats.new.exe"
UPDATE_BAT_NAME = "_apply_update.bat"

# 本地内置更新日志（离线也能查看）；服务器 version.json 的 changelog 用于提示新版本内容。
CHANGELOG = [
    {"version": "1.1.8", "date": "2026-11-13", "items": [
        "概览卡高度启动时即固定，网络数据加载完成后整页不再跳动",
        "修复每日统计表格「日期 / 场次 / 积分 / 总耗时」四列空白的问题",
    ]},
    {"version": "1.1.7", "date": "2026-11-13", "items": [
        "勇士等级计算「升到等级」默认填「起始等级 +10」，打开即给出升级预测",
        "移除顶栏「刷新」按钮，数据更新由常驻后台自动刷新（每 5 秒一轮）完成",
        "概览卡「距下一级还差」数值放大并改用强调色，关键缺口更醒目",
        "每日统计内容字号放大，表格更易读",
    ]},
    {"version": "1.1.6", "date": "2026-11-13", "items": [
        "移除顶栏「自动刷新 · 每轮间隔 N 秒」勾选配置，自动刷新改为常驻后台无感知运行（不再提供开关与间隔配置）",
    ]},
    {"version": "1.1.5", "date": "2026-11-12", "items": [
        "版本自动检查失败时，徽章旁新增「重试检查」按钮，可手动重新获取服务器版本（点击徽章亦可触发重试）",
    ]},
    {"version": "1.1.4", "date": "2026-11-11", "items": [
        "三个业务接口（排行榜 / 会员赛季资料 / 近期战绩）各自独立成败：某接口失败只跳过该区块、保留上一轮旧内容，状态栏提示失败接口",
        "近期战绩标题旁的「(最近 N 场)」数量文案改为固定提示「点击可排序」",
    ]},
    {"version": "1.1.3", "date": "2026-11-11", "items": [
        "「更新日志」支持点击窗口外任意位置关闭：点主窗口、其它窗口或桌面导致失焦即自动关闭，右上角红叉与「关闭」按钮照常可用",
        "点击「更新日志」按钮本身不会误关窗口；「发现新版本」提示窗保持原样，避免误点打断下载",
    ]},
    {"version": "1.1.2", "date": "2026-11-11", "items": [
        "重做「发现新版本」提示窗：高度随内容收缩、按钮常驻底部、滚动条按需出现，不再有大片空白或按钮被挤出屏幕",
        "更新内容改为版本分层卡片：版本号高亮、条目悬挂缩进，长句不再错位折行；「更新日志」窗口同步改版",
    ]},
    {"version": "1.1.1", "date": "2026-11-11", "items": [
        "放宽启动版本检查超时至 10 秒，避免冷启动首次请求被静默跳过",
        "优化更新包下载：一次性读取响应体再分块写盘，9 MB 下载由数分钟缩短到约 8 秒",
    ]},
    {"version": "1.1.0", "date": "2026-11-11", "items": [
        "新增版本检查：启动后读取服务器最新版本，发现新版本弹窗提示（可关闭、不强制更新）",
        "新增可选自动更新：点击「立即更新」下载新版 exe，退出后自动替换并重启",
        "右上角新增「更新日志」入口与当前版本号显示",
    ]},
    {"version": "1.0.2", "date": "2026-11-11", "items": [
        "自动刷新改为无感知：不改鼠标光标、不反复改写状态栏，数据未变不重建表格",
        "近期战绩表头支持三态排序：升序 → 降序 → 恢复原始顺序",
    ]},
    {"version": "1.0.1", "date": "2026-11-11", "items": [
        "新增每轮完成后间隔 5 秒的自动刷新与开关",
        "收紧超时口径（token 10 秒 / 业务接口 5 秒），接口失败在状态栏给出提示",
    ]},
    {"version": "1.0.0", "date": "2026-11-11", "items": [
        "初始版本：近期战绩、每日统计、会员与勇士等级面板",
        "会员 / 勇士等级公式与升级预测、英雄名映射",
    ]},
]


def load_json(name):
    p = os.path.join(APP_DIR, name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"未找到 {name}，请将其放在程序同目录下")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)
