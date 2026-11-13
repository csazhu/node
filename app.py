"""10v10AI 数据面板 - 原生 Windows 窗口版"""

import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.client import HTTPSConnection

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    print("需要 Python 3.8+，请先安装 Python（自带 tkinter）")
    sys.exit(1)

APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

FIREBASE_API_KEY = "AIzaSyCKOLF7HtJf-JLF4rU7i8gxk-dZvWgPEfw"
API_BASE = "https://windy10v10ai.com"
TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

# ================= 自动刷新 / 取数重试口径 =================
# 只有勾上「自动刷新」才启用：一轮刷新「完成后」再等 5 秒发起下一轮，保证请求不堆叠。
AUTO_REFRESH_INTERVAL_MS = 5000
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


# ================= HTTP =================
def _proxy_host():
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def _build_opener():
    """带系统代理支持的 opener"""
    proxy = _proxy_host()
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler())
    return urllib.request.build_opener(*handlers)


_opener = _build_opener()


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def http_json(url, method="GET", headers=None, data=None, timeout=API_TIMEOUT):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with _opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_id_token(refresh_token, timeout=TOKEN_TIMEOUT):
    data = http_json(
        TOKEN_URL,
        method="POST",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=timeout,
    )
    return data["id_token"]


def api_get(token, url, timeout=API_TIMEOUT):
    return http_json(url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)


# ================= 版本 / 更新（纯逻辑，可离线测试） =================
def version_tuple(text):
    """'v1.2.3' / '1.2' → (1, 2, 3)；忽略非数字段，最多取 4 段。"""
    nums = [int(x) for x in re.findall(r"\d+", str(text or ""))][:4]
    return tuple(nums) if nums else (0,)


def is_newer(remote, local):
    """服务器版本是否高于本地版本；位数不足补 0，1.2 == 1.2.0。"""
    r, l = version_tuple(remote), version_tuple(local)
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def fetch_version_info(url=VERSION_URL, timeout=VERSION_TIMEOUT):
    """读取服务器版本清单；也接受本地路径 / file:// 便于离线验证。"""
    path = url[7:] if url.startswith("file://") else url
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return http_json(url, timeout=timeout)


def new_changelog_entries(info, local_version=APP_VERSION):
    """取服务器 changelog 里比本地版本新的条目，按版本降序。"""
    entries = [
        e for e in (info or {}).get("changelog", [])
        if is_newer(e.get("version"), local_version)
    ]
    return sorted(entries, key=lambda e: version_tuple(e.get("version")), reverse=True)


def download_file(url, dest, progress=None, timeout=DOWNLOAD_TIMEOUT, chunk=65536):
    """下载更新包并校验 PE 头（MZ），避免把 404 页面写成 exe。

    必须一次性 read() 读完响应体再分块写盘：经代理逐块 read(chunk) 时每块
    都要等一次网络往返，9 MB 实测约 279 秒；一次性读取约 8 秒。
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/octet-stream"})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            total = int(resp.headers.get("Content-Length") or 0) or len(data)
        with open(dest, "wb") as f:
            done = 0
            for start in range(0, len(data), chunk):
                piece = data[start:start + chunk]
                f.write(piece)
                done += len(piece)
                if progress:
                    progress(done, total)
            if not data and progress:
                progress(0, total)
        with open(dest, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("下载内容不是有效的 Windows 程序，已放弃更新")
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    return dest


def build_update_bat(pid, target, new):
    """纯 ASCII 替换脚本：路径靠 %~dp0 展开，放在中文目录下也不会乱码。

    主进程退出前 move 会失败，循环重试直到 exe 可覆盖，再启动新版本并自删。
    """
    return "\r\n".join([
        "@echo off",
        "setlocal",
        'cd /d "%~dp0"',
        f"set PID={int(pid)}",
        f"set TARGET={target}",
        f"set NEW={new}",
        "set /a N=0",
        ":wait",
        'move /Y "%NEW%" "%TARGET%" >nul 2>&1',
        "if not errorlevel 1 goto ok",
        "ping -n 2 127.0.0.1 >nul",
        "set /a N+=1",
        "if %N% LSS 60 goto wait",
        "echo Replace failed. Rename %NEW% manually. > update-error.log",
        'del "%~f0"',
        "exit /b 1",
        ":ok",
        'start "" "%TARGET%"',
        'del "%~f0"',
        "exit /b 0",
        "",
    ])


def apply_update(new_path, target_path=None, pid=None):
    """写替换脚本并拉起；调用方随后关闭主窗口即可完成覆盖 + 重启。"""
    target_path = target_path or os.path.join(APP_DIR, UPDATE_EXE_NAME)
    pid = os.getpid() if pid is None else pid
    bat = os.path.join(APP_DIR, UPDATE_BAT_NAME)
    with open(bat, "w", encoding="ascii", newline="") as f:
        f.write(build_update_bat(pid, os.path.basename(target_path), os.path.basename(new_path)))
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd.exe", "/c", bat], cwd=APP_DIR, **kwargs)
    return bat


# ================= 数据处理 =================
def get_game_date(utc_str, tz, start_hour):
    """按 start_hour 点为界划分游戏日，返回 YYYY-MM-DD"""
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(tz)
    if dt.hour < start_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def local_time_str(utc_str, tz):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(sec):
    m, s = divmod(int(sec or 0), 60)
    return f"{m}:{s:02d}"


# ================= 战绩表排序键 =================
def _difficulty_sort_key(r):
    """N1~N8 按难度数字排，「自定义」排在数字难度之后。"""
    d = r.get("difficulty", "")
    if d.startswith("N") and d[1:].isdigit():
        return (0, int(d[1:]))
    return (1, 0)


# 用原始数值排序，不用带千分位/单位的显示字符串
SORT_KEYS = {
    "time": lambda r: r.get("time", ""),
    "difficulty": _difficulty_sort_key,
    "hero": lambda r: r.get("hero", ""),
    "duration": lambda r: r.get("durationSec", 0),
    "bp": lambda r: r.get("battlePoints", 0),
    "level": lambda r: r.get("level", 0),
    "kda": lambda r: (r.get("kills", 0) + r.get("assists", 0)) / max(r.get("deaths", 0), 1),
    "lh": lambda r: r.get("lastHits", 0),
    "gold": lambda r: r.get("gold", 0),
    "hdmg": lambda r: r.get("heroDamage", 0),
    "tdmg": lambda r: r.get("damageTaken", 0),
    "tower": lambda r: r.get("towerKills", 0),
}


# ================= 等级经验规则 =================
# 首个升级需 1000 经验，之后每升一级所需经验递增 step。
# base 是「游戏显示等级」里对应 1000 经验的那一级起点，用于和网站接口对齐：
#   会员 step=50  base=1  → 20→21 需 1950（接口 memberNextLevelPoint）
#   勇士 step=100 base=10 → 71→72 需 7100（接口 seasonNextLevelPoint）
MEMBER_STEP, MEMBER_BASE = 50, 1
WARRIOR_STEP, WARRIOR_BASE = 100, 10


def level_need(level, step, base):
    """level → level+1 所需经验"""
    return 1000 + step * (level - base)


def level_cum(level, step, base):
    """1 级 0 经验 → level 级 的累计经验"""
    n = max(0, level - 1)
    return 1000 * n + step * (n * (n + 1) // 2 - base * n)


def level_from_exp(total, step, base):
    """由累计经验反推当前等级（游戏显示口径）"""
    lv = 1
    while lv < 100000 and level_cum(lv + 1, step, base) <= total:
        lv += 1
    return lv


class DataFetcher:
    def __init__(self, cfg, heroes):
        self.cfg = cfg
        self.heroes = heroes
        self.api_timeout = float(cfg.get("apiTimeout", API_TIMEOUT))
        self.token_timeout = float(cfg.get("tokenTimeout", TOKEN_TIMEOUT))
        self._token = None
        self._token_at = 0.0

    def _get_token(self):
        """id_token 缓存 50 分钟：短间隔的重复取数没必要每次都换 token。"""
        if self._token and time.monotonic() - self._token_at < TOKEN_CACHE_TTL:
            return self._token
        try:
            token = refresh_id_token(self.cfg["refreshToken"], timeout=self.token_timeout)
        except Exception:
            # 刷新失败就丢弃旧凭证，线程内重试时重新取，别拿过期 token 把 5 次耗尽
            self._token = None
            raise
        self._token = token
        self._token_at = time.monotonic()
        return token

    # ---------- 单接口独立获取（各走各自线程，互不阻塞） ----------
    def fetch_ranking(self):
        """排行榜：单一接口独立请求，失败由调用方（collect / 刷新线程）捕获容错。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/ranking",
                      timeout=self.api_timeout)

    def fetch_info(self):
        """会员 / 赛季资料：单一接口独立请求。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/info?include=member",
                      timeout=self.api_timeout)

    def fetch_recent(self):
        """近期战绩：单一接口独立请求。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/stats/recent",
                      timeout=self.api_timeout)

    def derive_rows_days(self, recent):
        """把原始近期战绩聚合为战绩明细 rows 与每日统计 days（含平均时长）。

        纯计算、无网络；collect 与并行刷新线程共用同一份逻辑，保证两份路径结果一致。
        """
        matches = recent if isinstance(recent, list) else (
            recent.get("matches") if isinstance(recent, dict) else None) or []
        durations = [int(m.get("durationSec") or 0) for m in matches if m.get("durationSec")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        tz = timezone(timedelta(hours=self.cfg.get("tzOffset", 8)))
        start_hour = self.cfg.get("gameDayStartHour", 8)
        task_points = self.cfg.get("taskPoints", 300)

        # 每日统计
        by_date = {}
        for m in matches:
            if not m.get("endedAt"):
                continue
            d = get_game_date(m["endedAt"], tz, start_hour)
            e = by_date.setdefault(d, {"count": 0, "points": 0, "minutes": 0.0})
            e["count"] += 1
            e["points"] += int(m.get("battlePoints") or 0)
            e["minutes"] += (m.get("durationSec") or 0) / 60

        days = []
        for d in sorted(by_date, reverse=True):
            e = by_date[d]
            total_min = round(e["minutes"])
            h, m = divmod(total_min, 60)
            eff = (e["points"] - task_points) / (e["minutes"] / 60) if e["minutes"] else 0
            days.append(
                {
                    "date": d,
                    "count": e["count"],
                    "points": e["points"],
                    "time": f"{h}时{m}分" if h else f"{m}分",
                    "eff": eff,
                }
            )

        # 战绩明细
        rows = []
        for m in matches:
            key = (m.get("heroName") or "").replace("npc_dota_hero_", "")
            hero = self.heroes.get(key, key)
            diff = m.get("difficulty")
            rows.append(
                {
                    "time": local_time_str(m["endedAt"], tz) if m.get("endedAt") else "",
                    "difficulty": f"N{diff}" if isinstance(diff, int) and 1 <= diff <= 8 else "自定义",
                    "level": m.get("level") or 0,
                    "hero": hero,
                    "awaken": (m.get("awaken") or 0) > 0,
                    "disconnected": bool(m.get("isDisconnected")),
                    "win": bool(m.get("win")),
                    "durationText": fmt_duration(m.get("durationSec")),
                    "durationSec": int(m.get("durationSec") or 0),
                    "kills": m.get("kills") or 0,
                    "deaths": m.get("deaths") or 0,
                    "assists": m.get("assists") or 0,
                    "lastHits": m.get("lastHits") or 0,
                    "gold": m.get("totalGoldEarned") or 0,
                    "heroDamage": m.get("heroDamage") or 0,
                    "damageTaken": m.get("damageTaken") or 0,
                    "towerKills": m.get("towerKills") or 0,
                    "battlePoints": m.get("battlePoints") or 0,
                }
            )
        return rows, days, avg_duration

    def build_profile(self, ranking, info):
        """把排行榜 + 会员/赛季资料原始响应聚合为 profile 字段（供 collect 兜底用）。"""
        info = info or {}
        ranking = ranking or {}
        return {
            "rank": ranking.get("rank", "-"),
            "seasonLevel": info.get("seasonLevel"),
            "seasonNeed": (
                (info.get("seasonNextLevelPoint") or 0) - (info.get("seasonCurrrentLevelPoint") or 0)
                if info.get("seasonLevel") is not None
                else None
            ),
            "memberLevel": info.get("memberLevel"),
            "memberNeed": (
                (info.get("memberNextLevelPoint") or 0) - (info.get("memberCurrentLevelPoint") or 0)
                if info.get("memberLevel") is not None
                else None
            ),
            "matchCount": info.get("matchCount"),
            "winCount": info.get("winCount"),
            # 等级预测 / 勇士计算用原始经验值
            "memberPointTotal": info.get("memberPointTotal") or 0,
            "memberCurrPoint": info.get("memberCurrentLevelPoint") or 0,
            "memberNextPoint": info.get("memberNextLevelPoint") or 0,
            "seasonPointTotal": info.get("seasonPointTotal") or 0,
            "seasonCurrPoint": info.get("seasonCurrrentLevelPoint") or 0,
            "seasonNextPoint": info.get("seasonNextLevelPoint") or 0,
        }

    def collect(self):
        """兼容聚合入口（测试 / 兜底）：串行取三接口后聚合。

        内部仍走 fetch_* + derive/build，逻辑与并行刷新完全一致；
        各接口独立异常容错：单个失败记入 warnings/failed，由渲染层跳过该区块。
        token 失败则整体抛 RuntimeError（与单接口失败区分开）。
        """
        try:
            self._get_token()
        except Exception as e:
            self._token = None  # 凭证可能已失效，下一轮强制重新获取
            raise RuntimeError(f"登录凭证刷新失败（{type(e).__name__}）: {e}") from e

        warnings = []
        failed = set()

        def safe(fn, label):
            try:
                return fn()
            except Exception as e:
                # 单个接口失败不影响其它接口：记入失败清单，由渲染层跳过该区块更新
                warnings.append(f"{label} 请求失败（{type(e).__name__}）")
                failed.add(label)
                return None

        ranking = safe(self.fetch_ranking, "排行榜")
        info = safe(self.fetch_info, "会员/赛季资料")
        recent = safe(self.fetch_recent, "近期战绩")
        rows, days, avg_duration = self.derive_rows_days(recent)
        profile = self.build_profile(ranking, info)
        return {
            "profile": profile,
            "days": days,
            "rows": rows,
            "avgDurationSec": avg_duration,
            "warnings": warnings,
            "failed": list(failed),
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class FetchCancelled(Exception):
    """所属线程组已被新一组抢占或窗口已关闭：立刻放弃取数，不再入队结果。"""


def fetch_with_retry(fn, cancel, max_attempts=FETCH_MAX_ATTEMPTS,
                     retry_s=FETCH_RETRY_INTERVAL_S):
    """单接口取数：成功即返回 (data, None)，失败最多尝试 max_attempts 次。

    每次失败后等 retry_s 秒再试；取消事件置位时立即唤醒并抛 FetchCancelled，
    「旧组被抢占」时旧线程不必等满间隔就退出。用尽次数仍失败返回 (None, 最后一次错误)。
    cancel 为 threading.Event，由所属线程组持有。
    """
    limit = max(1, int(max_attempts))
    last_err = None
    for attempt in range(1, limit + 1):
        if cancel is not None and cancel.is_set():
            raise FetchCancelled()
        try:
            return fn(), None
        except Exception as e:  # 网络 / 解析异常都算一次失败，交给下一次尝试
            last_err = f"{type(e).__name__}: {e}"
            if attempt >= limit:
                break
            if cancel is not None:
                if cancel.wait(retry_s):  # 被抢占/关窗时不再等满 0.5 秒
                    raise FetchCancelled()
            elif retry_s > 0:
                time.sleep(retry_s)
    return None, last_err


# ================= 自动刷新调度 =================
class RefreshController:
    """纯逻辑调度器（不依赖 tkinter）：一次刷新完成后等 interval_ms 再发起下一轮。

    after / after_cancel 由外部注入，便于无 GUI 自测：
      tkinter -> root.after / root.after_cancel；测试 -> 记录延迟的假时钟。
    """

    def __init__(self, after, after_cancel, start_refresh, interval_ms=AUTO_REFRESH_INTERVAL_MS):
        self._after = after
        self._after_cancel = after_cancel
        self._start_refresh = start_refresh
        self.interval_ms = int(interval_ms)
        self.enabled = True
        self.running = False
        self.stopped = False
        self.rounds = 0
        self._timer = None

    def _cancel_timer(self):
        if self._timer is not None:
            try:
                self._after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

    def schedule(self, delay_ms=None):
        """安排下一轮；已有定时器会被重置。返回是否成功安排。"""
        if self.stopped or not self.enabled or self.running:
            return False
        self._cancel_timer()
        delay = self.interval_ms if delay_ms is None else int(delay_ms)
        self._timer = self._after(delay, self.tick)
        return True

    def tick(self):
        """定时器到期：发起一轮刷新。"""
        self._timer = None
        if self.stopped or not self.enabled:
            return False
        return self.request()

    def request(self):
        """立即发起一轮（手动按钮与自动 tick 共用）；刷新中或已停止则忽略。"""
        if self.stopped or self.running:
            return False
        self._cancel_timer()
        self.running = True
        self.rounds += 1
        try:
            self._start_refresh()
        except Exception:
            self.running = False
            raise
        return True

    def finished(self):
        """一轮刷新结束（成功或失败）：重新安排 5 秒后的下一轮。"""
        if self.stopped:
            return False
        self.running = False
        return self.schedule()

    def set_enabled(self, enabled):
        """自动刷新开关；关闭时取消待触发的定时器，打开时立即开始一轮。"""
        self.enabled = bool(enabled)
        if not self.enabled:
            self._cancel_timer()
            return False
        if not self.running:
            return self.schedule(0)
        return False

    def stop(self):
        """窗口关闭：不再发起任何新请求或定时器。"""
        self.stopped = True
        self._cancel_timer()


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


class ChangelogWindow(tk.Toplevel):
    """深色卡片式只读窗口：高度随内容收缩，按钮常驻底部，滚动条按需出现。"""

    WIDTH_CHARS = 80
    OUTSIDE_CLOSE_DELAY_MS = 150   # 跳过开窗瞬间的焦点抖动，避免刚弹出就自关

    def __init__(self, master, title, subtitle, entries, show_close=True,
                 close_text="关闭", headline=None, close_on_focus_out=False,
                 toggle_widget=None):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.transient(master)
        self.resizable(False, True)
        self.minsize(480, 220)
        self._close_on_focus_out = close_on_focus_out
        self._toggle_widget = toggle_widget
        self._outside_binds = []
        self._outside_armed = False

        head = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S4, S5, S3))
        head.pack(fill="x")
        title_row = ttk.Frame(head, style="Dark.TFrame")
        title_row.pack(fill="x")
        tk.Frame(title_row, bg=ACCENT, width=3, height=20).pack(side="left", padx=(0, S2))
        ttk.Label(title_row, text=headline or title, style="Head.TLabel").pack(side="left")
        if subtitle:
            ttk.Label(head, text=subtitle, style="Muted.TLabel", wraplength=580).pack(
                anchor="w", pady=(S2, 0)
            )

        body = ttk.Frame(self, style="Dark.TFrame", padding=(S5, 0, S5, 0))
        body.pack(fill="both", expand=True)
        height, need_scroll = _changelog_metrics(entries)
        self.text = tk.Text(
            body, wrap="word", height=height, width=self.WIDTH_CHARS,
            bg=PANEL, fg=TEXT, bd=0, relief="flat",
            highlightbackground=LINE, highlightthickness=1,
            padx=S4, pady=S3, insertbackground=TEXT,
            font=(FONT_UI, 10),
        )
        self.text.tag_configure("version", foreground=ACCENT,
                                font=(FONT_UI, 11, "bold"), spacing1=6)
        self.text.tag_configure("date", foreground=FAINT,
                                font=(FONT_UI, 9))
        self.text.tag_configure("item", lmargin1=4, lmargin2=24,
                                spacing1=2, spacing3=5)
        self.text.tag_configure("bullet", foreground=ACCENT)
        self.text.tag_configure("blank", spacing1=0, spacing3=0,
                                font=(FONT_UI, 4))
        self.sb = ttk.Scrollbar(
            body, orient="vertical", command=self.text.yview,
            style="Dark.Vertical.TScrollbar"
        )
        self.text.configure(yscrollcommand=self.sb.set)
        if need_scroll:
            self.sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        _render_changelog(self.text, entries)

        self.action_bar = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S3, S5, S4))
        self.action_bar.pack(fill="x")
        self.btn_close = None
        if show_close:
            self.btn_close = ttk.Button(
                self.action_bar, text=close_text, command=self.destroy, style="Ghost.TButton"
            )
            self.btn_close.pack(side="right")
        self._center_on_master()
        if close_on_focus_out:
            # 「更新日志」是纯查看窗口，点窗口外任意位置即关闭；「发现新版本」
            # 带下载操作，保持原行为，避免误点打断更新。
            self.after(self.OUTSIDE_CLOSE_DELAY_MS, self._arm_outside_close)

    def _arm_outside_close(self):
        """延迟绑定：FocusOut 覆盖切到别的应用/桌面，主窗口点击作为兜底。"""
        try:
            if not self.winfo_exists():
                return
            self._outside_armed = True
            self._track_bind(self, "<FocusOut>", self._on_focus_out)
            self._track_bind(self.master, "<ButtonPress-1>", self._on_master_press)
        except tk.TclError:
            pass  # 窗口已被用户关掉

    def _track_bind(self, widget, sequence, func):
        before = widget.bind(sequence)
        funcid = widget.bind(sequence, func, add="+")
        # 记下本次追加的脚本片段：tkinter 的 unbind(seq, funcid) 会清掉该 widget
        # 上这个事件的全部绑定，主窗口上不能这么用，只能精确摘除自己那一段。
        added = widget.bind(sequence)[len(before):]
        self._outside_binds.append((widget, sequence, funcid, added))

    def _on_focus_out(self, event=None):
        # 焦点切换过程中 focus_get() 可能短暂为空，等事件处理完再判断是否真的离开
        self.after_idle(self._close_if_focus_left)

    def _on_master_press(self, event=None):
        if event is not None and self._toggle_widget is not None \
                and event.widget is self._toggle_widget:
            return  # 点的是「更新日志」按钮本身，交给按钮命令复用窗口
        self.after_idle(self._close_if_click_outside, event)

    def _close_if_click_outside(self, event):
        """主窗口内任意组件（排行榜卡片/表头/按钮…）被点击即关闭；窗口内点击不关。

        用点击目标的组件层级判断，而非焦点——ttk 标签、卡片默认不抢焦点，
        点它们时焦点仍停留在更新日志窗口，单纯看焦点会误判成「窗口内」而关不掉。
        """
        if not self._outside_armed:
            return
        try:
            if not self.winfo_exists():
                return
            widget = event.widget if event is not None else None
            if widget is self._toggle_widget:
                return
            w = widget
            while w is not None:
                if w is self:
                    return  # 点的是更新日志窗口内部，不关闭
                w = getattr(w, "master", None)
            self.destroy()
        except tk.TclError:
            pass

    def _close_if_focus_left(self):
        """焦点已不在本窗口（含整个应用失焦）时关闭；窗口内切换焦点不关。"""
        if not self._outside_armed:
            return
        try:
            if not self.winfo_exists():
                return
            focus = self.focus_get()
            if focus is self._toggle_widget and self._toggle_widget is not None:
                return
            if focus is None:
                self.destroy()
                return
            widget = focus
            while widget is not None:
                if widget is self:
                    return
                widget = getattr(widget, "master", None)
            self.destroy()
        except tk.TclError:
            pass

    def destroy(self):
        for widget, sequence, funcid, added in self._outside_binds:
            try:
                script = widget.bind(sequence)
                if added and added in script:
                    widget.bind(sequence, script.replace(added, "", 1))
                widget.deletecommand(funcid)
            except (tk.TclError, TypeError):
                pass
        self._outside_binds.clear()
        self._outside_armed = False
        super().destroy()

    def _center_on_master(self):
        """相对主窗口居中；请求尺寸不依赖窗口是否已映射。"""
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = self.master.winfo_rootx() + (self.master.winfo_width() - w) // 2
            y = self.master.winfo_rooty() + (self.master.winfo_height() - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass


class UpdateWindow(ChangelogWindow):
    """非模态提示窗：可随时关闭，关闭后照常使用当前版本，绝不强制更新。"""

    def __init__(self, master, app, info):
        self._info = info
        self.app = app
        entries = new_changelog_entries(info)
        if not entries:
            entries = [{
                "version": info.get("version", "?"),
                "items": [info.get("notes") or "请前往下载页查看本次更新内容。"],
            }]
        super().__init__(
            master,
            title="发现新版本",
            headline=f"v{APP_VERSION}   →   v{info.get('version', '?')}",
            subtitle="有新版本可用，可关闭本窗口继续使用当前版本，不会强制更新",
            entries=entries,
            show_close=False,
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.pbar = ttk.Progressbar(
            self, style="Update.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        self.lbl_state = ttk.Label(self.action_bar, text="", style="Muted.TLabel")
        self.lbl_state.pack(side="left", padx=(0, 10))
        self.btn_update = tk.Button(
            self.action_bar, text="立即更新", command=self._on_update,
            bg=ACCENT, fg=BG, activebackground=ACCENT_HOVER, activeforeground=BG,
            disabledforeground=MUTED, relief="flat", bd=0, padx=S4, pady=5,
            font=(FONT_UI, 10, "bold"), cursor="hand2",
        )
        self.btn_update.pack(side="right", padx=(0, 8))
        self.btn_later = ttk.Button(
            self.action_bar, text="稍后再说", command=self.destroy, style="Update.TButton"
        )
        self.btn_later.pack(side="right")

    def _on_update(self):
        self.app.start_update(self._info, self)

    def _on_restart(self):
        self.app.finish_update(self)

    def set_busy(self):
        self.btn_update.configure(state="disabled", text="正在下载...")
        self.lbl_state.configure(text="正在下载更新包...")
        self.pbar.configure(value=0)
        self.pbar.pack(fill="x", padx=18, pady=(0, 4), before=self.action_bar)

    def set_progress(self, done, total):
        if total:
            self.pbar.configure(maximum=total, value=min(done, total))
            self.lbl_state.configure(text=f"正在下载更新包... {done * 100 // total}%")
        else:
            self.lbl_state.configure(text=f"正在下载更新包... {done / 1048576:.1f} MB")

    def set_ready(self):
        self.pbar.pack_forget()
        self.btn_update.configure(state="normal", text="重启并完成更新", command=self._on_restart)
        self.lbl_state.configure(text="更新包已就绪，点击后程序将关闭并自动重启")

    def set_error(self, msg):
        self.pbar.pack_forget()
        self.btn_update.configure(state="normal", text="重试", command=self._on_update)
        self.lbl_state.configure(text=f"更新失败：{msg}")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("10v10AI 数据面板")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG)
        self.rows = []
        self.filtered = []
        self.days = []
        # 持久缓存各接口最后一次成功的数据；某接口失败时保留旧值、不更新界面
        self.profile = {
            "rank": "-",
            "seasonLevel": None,
            "seasonNeed": None,
            "memberLevel": None,
            "memberNeed": None,
            "matchCount": None,
            "winCount": None,
            "memberPointTotal": 0,
            "memberCurrPoint": 0,
            "memberNextPoint": 0,
            "seasonPointTotal": 0,
            "seasonCurrPoint": 0,
            "seasonNextPoint": 0,
        }
        self.avg_duration = 0
        self._card_signature = None
        self.member_open = True
        # 战绩表排序：0=原始顺序 / 1=升序 / 2=降序
        self.sort_col = None
        self.sort_state = 0
        self.tree_headers = {}
        # 无感知刷新：只在必要时更新界面，不打断用户
        self._rendered_once = False
        self._error_shown = False
        self._rows_rendered = False
        self._days_rendered = False
        self._mem_signature = None
        # 各接口独立比对：记录每个接口「上次写入」的内容，变了才更新对应区块
        self._last_rank = None
        self._last_info_fields = None
        self._round = None  # 当前有效线程组的三接口聚合状态
        # 线程组：每组带自增 seq 与 cancel 事件。新组抢占旧组，旧线程快速退出、
        # 旧结果按 seq 丢弃；同一时刻只有一组线程在取数（R009 主线程渲染不变）。
        self._fetch_seq = 0
        self._fetch_busy = False
        self._manual_busy = False
        self._round_cancel = threading.Event()
        self._round_threads = []
        # 手动刷新按钮的「刷新中」旋转动画状态
        self._spin_active = False
        self._spin_timer = None
        self._spin_idx = 0

        self.cfg = load_json("config.json")
        self.task_points = self.cfg.get("taskPoints", 300)
        self.heroes = load_json("heroes.json")
        self.fetcher = DataFetcher(self.cfg, self.heroes)

        self._closed = False
        # 子线程只往队列放结果，主线程轮询取回，避免跨线程调用 Tk（不稳定且会漏回调）
        self._results = queue.Queue()
        # 版本检查 / 更新下载用独立队列，不与取数结果混在一起；子线程只入队。
        self._updates = queue.Queue()
        self._update_polling = False
        self._update_active = False
        self._version_checking = False
        # 启动即视为已查过版本：首轮自动刷新不立刻重复查，避免每 5 秒轮询服务器；
        # 之后每满 VERSION_CHECK_MIN_INTERVAL_MS 在自动刷新里静默复查一次。
        self._last_version_check = time.monotonic()
        # 变更比对：上次「写入」的数据/版本快照，一致则跳过本轮写入（避免每轮无谓重绘/闪烁）
        self._last_data_sig = None
        self._last_version_state = None
        self._last_remote_version = None
        self._update_window = None
        self._changelog_window = None
        self._new_exe = None
        # 自动刷新默认不开启：顶栏小勾未勾上时不安排 5 秒轮询；
        # config.json 可用 autoRefresh=1 改默认值（0/1）。
        auto_on = bool(int(self.cfg.get("autoRefresh", 0) or 0))
        self.auto_var = tk.IntVar(value=1 if auto_on else 0)
        self.ctrl = RefreshController(
            after=self.root.after,
            after_cancel=self.root.after_cancel,
            start_refresh=self._begin_fetch,
            interval_ms=int(self.cfg.get("autoRefreshIntervalMs", AUTO_REFRESH_INTERVAL_MS)),
        )
        if not auto_on:
            self.ctrl.set_enabled(False)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # 启动即取第一轮，延迟到事件循环（避免构造期同步起线程）。这一轮不经过
        # ctrl.request()，所以默认不勾时收尾也不会安排下一轮；勾上则由 ctrl 续跑。
        self.root.after(0, self._begin_fetch)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        # 表面：三层亮度建立层级，越靠上越亮；区块之间只用 1px 细线分隔
        style.configure("Dark.TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("Soft.TFrame", background=PANEL)
        style.configure("Day.TFrame", background=PANEL_SOFT)
        # 排版：标题 / 正文 / 辅助 三级，指标数值单独一级，不用大图标堆砌
        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 10))
        style.configure("Head.TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 16, "bold"))
        style.configure("Subhead.TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 12, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("Faint.TLabel", background=BG, foreground=FAINT, font=(FONT_UI, 9))
        style.configure("Error.TLabel", background=BG, foreground=DANGER, font=(FONT_UI, 9))
        style.configure("Chip.TLabel", background=PANEL_SOFT, foreground=MUTED,
                        font=(FONT_UI, 9), padding=(7, 3))
        # 排序提示：未排序=中性灰提示；排序中=强调色高亮，随点击切换、醒目
        style.configure("SortActive.TLabel", background=ACCENT_SOFT, foreground=ACCENT,
                        font=(FONT_UI, 9, "bold"), padding=(7, 3))
        style.configure("CardLabel.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("CardValue.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 24, "bold"))
        style.configure("CardSub.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        # 概览卡「距下一级还差 X」中的数值：放大并改用唯一强调色，形成关键焦点
        style.configure("CardSubNum.TLabel", background=PANEL, foreground=ACCENT,
                        font=(FONT_NUM, 14, "bold"))
        style.configure("Section.TLabel", background=BG, foreground=MUTED, font=(FONT_UI, 10, "bold"))
        style.configure("DayHead.TLabel", background=PANEL_SOFT, foreground=MUTED, font=(FONT_UI, 9, "bold"))
        style.configure("DayCell.TLabel", background=PANEL, foreground=TEXT, font=(FONT_NUM, 11))
        style.configure("DayCellNeg.TLabel", background=PANEL, foreground=DANGER, font=(FONT_NUM, 11))
        style.configure("TEntry", fieldbackground=PANEL_SOFT, foreground=TEXT,
                        insertbackground=ACCENT, borderwidth=1, padding=(6, 4))
        style.configure("Update.TButton", padding=(12, 5))
        style.configure(
            "Update.Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL_SOFT,
            bordercolor=PANEL_SOFT, lightcolor=ACCENT, darkcolor=ACCENT,
        )
        # 按钮层级：Filled(Primary) > Ghost > Text；次要操作一律不加实心底
        style.configure("TButton", background=PANEL_SOFT, foreground=TEXT,
                        borderwidth=0, padding=(14, 6), font=(FONT_UI, 10))
        style.configure("Primary.TButton", background=ACCENT, foreground=BG,
                        borderwidth=0, padding=(18, 7), font=(FONT_UI, 10, "bold"))
        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                        borderwidth=1, relief="solid", bordercolor=LINE,
                        padding=(12, 6), font=(FONT_UI, 10))
        # clam 默认把 TButton 的 active 背景映射成近白色 #eeebe7，而界面文字是
        # 浅色 TEXT；只 configure 改不掉状态映射，悬停就会白底白字。这里把
        # active / pressed / disabled 的背景与前景成对覆盖，保证任何状态都可读。
        btn_bg = [("disabled", PANEL_SOFT), ("pressed", BTN_PRESSED), ("active", BTN_HOVER)]
        btn_fg = [("disabled", FAINT), ("pressed", TEXT), ("active", TEXT)]
        for btn_style in ("TButton", "Update.TButton", "Ghost.TButton"):
            style.map(
                btn_style,
                background=btn_bg,
                foreground=btn_fg,
                bordercolor=[("active", LINE)],
                lightcolor=[("active", BTN_HOVER), ("pressed", BTN_PRESSED)],
                darkcolor=[("active", BTN_HOVER), ("pressed", BTN_PRESSED)],
            )
        style.map(
            "Primary.TButton",
            background=[("disabled", PANEL_SOFT), ("pressed", BTN_PRESSED), ("active", ACCENT_HOVER)],
            foreground=[("disabled", FAINT), ("pressed", BG), ("active", BG)],
        )
        # 左侧两个面板与卡片同底色，避免「卡片套卡片」的廉价层次
        style.configure("Soft.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 10))
        style.configure("SoftMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("SoftHead.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 11, "bold"))
        style.configure("SoftValue.TLabel", background=PANEL, foreground=ACCENT, font=(FONT_UI, 11, "bold"))
        style.configure("SoftResult.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 11, "bold"))
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"Dark.{orient}.TScrollbar", background=LINE, troughcolor=BG,
                bordercolor=BG, arrowcolor=MUTED, relief="flat", arrowsize=8,
            )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", PANEL), ("readonly", PANEL)],
            foreground=[("disabled", FAINT)],
            bordercolor=[("focus", ACCENT), ("hover", LINE)],
        )

        # 先配置好两种表格样式，再创建控件
        self._style_tree(None, big=False)
        self._style_tree(None, big=True)

        # ---------- 应用头：左侧品牌与同步时间，右侧操作按主/次分层 ----------
        top = ttk.Frame(self.root, style="Dark.TFrame")
        top.pack(fill="x", padx=S5, pady=(S4, S3))
        tk.Frame(top, bg=ACCENT, width=3, height=38).pack(side="left", padx=(0, S3))
        brand = ttk.Frame(top, style="Dark.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="10v10AI 数据面板", style="Head.TLabel").pack(anchor="w")
        meta = ttk.Frame(brand, style="Dark.TFrame")
        meta.pack(anchor="w", pady=(2, 0))
        self.lbl_updated = ttk.Label(meta, text="", style="Muted.TLabel")
        self.lbl_updated.pack(side="left")
        ttk.Label(meta, text="  ·  个人战绩实时同步", style="Faint.TLabel").pack(side="left")
        # 先 pack 的靠右：更新日志在最右上角，旁边是版本徽章（当前版本 +
        # 服务器最新版本常驻可见，有新版才亮红点，由用户手动点开更新）。
        self.btn_changelog = ttk.Button(
            top, text="更新日志", style="Ghost.TButton", command=self._show_changelog
        )
        self.btn_changelog.pack(side="right")
        # 版本检查失败时出现的「重试检查」按钮：固定在徽章右侧，平时隐藏不占位
        # （外层 frame 始终占位在一处，仅内部按钮显隐，避免顶栏跳动或 pack 重排错位）。
        self._version_check_frame = ttk.Frame(top, style="Dark.TFrame")
        self._version_check_frame.pack(side="right", padx=(0, S2))
        self.btn_version_check = ttk.Button(
            self._version_check_frame, text="重试检查", style="Ghost.TButton",
            command=self._on_manual_version_check,
        )
        self.btn_version_check.pack_forget()  # 默认隐藏，_set_version_badge 在失败时显示
        self._build_version_badge(top)
        # 手动刷新按钮 + 自动刷新开关：按钮在上，小字勾选行在按钮左下方（左对齐），
        # 默认不勾（autoRefresh=0）；勾上才由 RefreshController 每 5 秒续跑一轮。
        # 按钮固定 width，避免「刷新」↔「◐ 刷新中」切换时顶栏宽度跳动（R026）。
        refresh_box = ttk.Frame(top, style="Dark.TFrame")
        refresh_box.pack(side="right", padx=(0, S4))
        self.btn_refresh = ttk.Button(
            refresh_box, text="刷新", style="Primary.TButton", width=10,
            command=self.refresh,
        )
        self.btn_refresh.pack(anchor="e")
        auto_row = ttk.Frame(refresh_box, style="Dark.TFrame")
        auto_row.pack(anchor="w", pady=(S1, 0))
        self.auto_chk = tk.Checkbutton(
            auto_row,
            text="自动刷新",
            variable=self.auto_var,
            command=self._on_auto_toggle,
            bg=BG,
            fg=MUTED,
            selectcolor=ACCENT_SOFT,
            activebackground=BG,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=(FONT_UI, 9),
        )
        self.auto_chk.pack(side="left")
        _divider(self.root)  # 应用头与内容之间的通栏细线

        # 概览指标：一整块面板 + 卡片间 1px 竖线，避免四个悬浮方块
        self.cards_frame = tk.Frame(
            self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1
        )
        self.cards_frame.pack(fill="x", padx=S5, pady=(S3, S3))
        for i in range(4):
            self.cards_frame.columnconfigure(i, weight=1, uniform="card")

        # 启动时即固定 4 张概览卡骨架并预留副文本行高度：避免数据加载后卡片从
        # 1 张变 4 张、高度撑开导致整页跳动（R040）。数据到了只更新文字，不重建。
        self._card_slots = []
        for i, clabel in enumerate(["排行榜排名", "赛季等级", "会员等级", "总场次"]):
            f = tk.Frame(self.cards_frame, bg=PANEL)
            f.grid(row=0, column=i, sticky="nsew", padx=(S4, S4), pady=(S2, S2))
            tk.Frame(f, bg=ACCENT if i == 0 else LINE, height=2, width=28).pack(
                anchor="w", pady=(0, S1)
            )
            ttk.Label(f, text=clabel, style="CardLabel.TLabel").pack(anchor="w")
            value = ttk.Label(f, text="—", style="CardValue.TLabel")
            value.pack(anchor="w", pady=(S1, 0))
            sub_frame = tk.Frame(f, bg=PANEL)
            sub_frame.pack(anchor="w", pady=(S1, 0))
            sub_l = ttk.Label(sub_frame, text="", style="CardSub.TLabel")
            sub_l.pack(side="left")
            sub_r = ttk.Label(sub_frame, text="", style="CardSubNum.TLabel")
            sub_r.pack(side="left")
            if i < 3:
                # 竖分隔线放在卡片内部，避免增加 cards_frame 的直接子控件数量
                tk.Frame(f, bg=LINE, width=1).place(relx=1.0, x=8, rely=0, relheight=1.0)
            self._card_slots.append({"value": value, "sub_l": sub_l, "sub_r": sub_r})
        # 用空数据先填一次骨架，保证加载前显示「— 名 / — 级」而非光秃秃的「—」
        self._render_cards()

        # 状态栏先占底部，再让主体填满剩余空间，避免内容过高把状态栏挤出窗口
        status_bar = ttk.Frame(self.root, style="Dark.TFrame")
        status_bar.pack(side="bottom", fill="x", padx=S5, pady=(S2, S3))
        self.status_dot = tk.Label(status_bar, text="●", bg=BG, fg=FAINT, font=(FONT_UI, 8), bd=0)
        self.status_dot.pack(side="left", padx=(0, S2))
        self.lbl_status = ttk.Label(status_bar, text="正在加载...", style="Muted.TLabel")
        self.lbl_status.pack(side="left")

        # 主体：左（每日统计 / 会员表 / 勇士表）/ 右战绩
        body = ttk.Frame(self.root, style="Dark.TFrame")
        body.pack(fill="both", expand=True, padx=S5, pady=(0, S3))
        body.columnconfigure(0, minsize=480)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左列整体可滚动，新增面板不会把窗口撑爆
        left_outer = ttk.Frame(body, style="Dark.TFrame")
        left_outer.grid(row=0, column=0, sticky="nsew")
        self.left_canvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0, width=464)
        left_sb = ttk.Scrollbar(
            left_outer, orient="vertical", command=self.left_canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side="right", fill="y", padx=(S2, 0))
        self.left_canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(self.left_canvas, style="Dark.TFrame")
        self._left_win = self.left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfig(self._left_win, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        # ---------- 每日统计：一个小节标题 + 带细线与斑马纹的数据表 ----------
        day_head = ttk.Frame(left, style="Dark.TFrame")
        day_head.pack(fill="x", pady=(0, S2))
        ttk.Label(day_head, text="每日统计", style="Subhead.TLabel").pack(side="left")
        ttk.Label(day_head, text="按游戏日汇总", style="Faint.TLabel").pack(side="right")

        day_wrap = tk.Frame(left, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        day_wrap.pack(fill="x")

        # 每日统计用 grid 布局，表头与内容严格对齐
        self.day_cols_def = (("日期", 116), ("场次", 66), ("积分", 92), ("总耗时", 88), ("效率", 86))
        head_row = ttk.Frame(day_wrap, style="Day.TFrame")
        head_row.pack(fill="x")
        for i, (text, w) in enumerate(self.day_cols_def):
            head_row.columnconfigure(i, minsize=w)
            tk.Label(
                head_row, text=text, bg=PANEL_SOFT, fg=MUTED,
                font=(FONT_UI, 12, "bold"), anchor="center", pady=6,
            ).grid(row=0, column=i, sticky="ew")
        _divider(day_wrap)

        self.day_rows_frame = tk.Frame(day_wrap, bg=PANEL)
        self.day_rows_frame.pack(fill="x")

        # ---------- 会员表：未来 100 级达成日期（一行 2 个，可折叠下拉 + 内部滚动） ----------
        mem_outer = tk.Frame(left, bg=LINE, padx=1, pady=1)
        mem_outer.pack(fill="x", pady=(S3, 0))
        mem_box = ttk.Frame(mem_outer, style="Soft.TFrame", padding=(S4, S2))
        mem_box.pack(fill="x")
        mem_head = ttk.Frame(mem_box, style="Soft.TFrame")
        mem_head.pack(fill="x")
        tk.Frame(mem_head, bg=ACCENT, width=3, height=18).pack(side="left", padx=(0, S2))
        self.mem_toggle = tk.Button(
            mem_head,
            text="会员等级预测（未来 100 级）  ▲",
            command=self._toggle_member,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL_SOFT,
            activeforeground=ACCENT,
            font=(FONT_UI, 11, "bold"),
            bd=0,
            relief="flat",
            anchor="w",
            cursor="hand2",
        )
        self.mem_toggle.pack(side="left")
        ttk.Label(mem_head, text="每日", style="SoftMuted.TLabel").pack(side="left", padx=(S3, S2))
        self.mem_daily = ttk.Entry(mem_head, width=6, justify="center")
        self.mem_daily.insert(0, "100")
        self.mem_daily.pack(side="left")
        self.mem_daily.bind("<KeyRelease>", lambda e: self._render_member_table())
        ttk.Label(mem_head, text="经验", style="SoftMuted.TLabel").pack(side="left", padx=(S1, 0))

        self.mem_summary = ttk.Label(mem_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.mem_summary.pack(anchor="w", pady=(S2, 0))

        self.mem_body = ttk.Frame(mem_box, style="Soft.TFrame")
        self.mem_body.pack(fill="x", pady=(S2, 0), after=self.mem_summary)
        self.mem_canvas = tk.Canvas(self.mem_body, bg=PANEL, highlightthickness=0, height=96)
        mem_sb = ttk.Scrollbar(
            self.mem_body, orient="vertical", command=self.mem_canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.mem_canvas.configure(yscrollcommand=mem_sb.set)
        mem_sb.pack(side="right", fill="y")
        self.mem_canvas.pack(side="left", fill="x", expand=True)
        self.mem_list = ttk.Frame(self.mem_canvas, style="Soft.TFrame")
        self._mem_win = self.mem_canvas.create_window((0, 0), window=self.mem_list, anchor="nw")
        self.mem_list.bind("<Configure>", lambda e: self.mem_canvas.configure(scrollregion=self.mem_canvas.bbox("all")))
        self.mem_canvas.bind("<Configure>", lambda e: self.mem_canvas.itemconfig(self._mem_win, width=e.width))

        # ---------- 勇士表：升级所需局数 / 小时 / 天数 ----------
        war_outer = tk.Frame(left, bg=LINE, padx=1, pady=1)
        war_outer.pack(fill="x", pady=(S2, 0))
        war_box = ttk.Frame(war_outer, style="Soft.TFrame", padding=(S4, S2))
        war_box.pack(fill="x")
        war_head = ttk.Frame(war_box, style="Soft.TFrame")
        war_head.pack(fill="x")
        tk.Frame(war_head, bg=ACCENT, width=3, height=18).pack(side="left", padx=(0, S2))
        ttk.Label(war_head, text="勇士等级计算（1000 起每级 +100）",
                  style="SoftHead.TLabel").pack(side="left")
        self.self_var = tk.IntVar(value=1)
        self.self_chk = tk.Checkbutton(
            war_head,
            text="是否是自己",
            variable=self.self_var,
            command=self._on_self_toggle,
            bg=PANEL,
            fg=TEXT,
            selectcolor=ACCENT_SOFT,
            activebackground=PANEL,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=(FONT_UI, 9),
        )
        self.self_chk.pack(side="right")
        self.war_info = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.war_info.pack(anchor="w", pady=(S2, S2))

        # 四个输入 2×2 排布：比四行更紧凑，结果区能更早进入视野
        grid = ttk.Frame(war_box, style="Soft.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="warcell")
        grid.columnconfigure(1, weight=1, uniform="warcell")
        entries = {}
        for idx, (label, default) in enumerate((
            ("起始等级", ""), ("升至等级", ""),
            ("平均每把积分", "105"), ("一天打多少把", "10"),
        )):
            cell = ttk.Frame(grid, style="Soft.TFrame")
            cell.grid(row=idx // 2, column=idx % 2, sticky="w", pady=S1)
            # 标签固定宽度 + 右对齐：不同字数（起始等级 4 字 / 平均每把积分 6 字）
            # 都占同样宽度，输入框左缘严格对齐，两列竖线成一条直线。
            ttk.Label(
                cell, text=label, style="SoftMuted.TLabel", width=12, anchor="e"
            ).pack(side="left")
            e = ttk.Entry(cell, width=8, justify="center")
            e.pack(side="left", padx=(S2, 0))
            if default:
                e.insert(0, default)
            e.bind("<KeyRelease>", lambda ev: self._render_warrior())
            entries[label] = e
        self.war_start = entries["起始等级"]
        self.war_target = entries["升至等级"]
        self.war_avg = entries["平均每把积分"]
        self.war_games = entries["一天打多少把"]

        tk.Frame(war_box, bg=LINE, height=1).pack(fill="x", pady=(S3, S2))
        self.war_res1 = ttk.Label(war_box, text="—", style="SoftValue.TLabel", wraplength=420)
        self.war_res1.pack(anchor="w", pady=(0, S1))
        self.war_res2 = ttk.Label(war_box, text="—", style="SoftResult.TLabel", wraplength=420)
        self.war_res2.pack(anchor="w", pady=(0, S1))
        self.war_hint = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.war_hint.pack(anchor="w", pady=(S1, 0))

        right = ttk.Frame(body, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(S4, 0))

        bar = ttk.Frame(right, style="Dark.TFrame")
        bar.pack(fill="x", pady=(0, S2))
        ttk.Label(bar, text="近期战绩", style="Subhead.TLabel").pack(side="left")
        self.lbl_sort_hint = ttk.Label(bar, text="点击可排序", style="Chip.TLabel")
        self.lbl_sort_hint.pack(side="left", padx=(S2, 0))
        ttk.Label(bar, text="输入英雄名搜索", style="Muted.TLabel").pack(side="right", padx=(S2, S2))
        self.search = ttk.Entry(bar, width=20)
        self.search.pack(side="right")
        self.search.insert(0, "")
        self.search.bind("<KeyRelease>", lambda e: self.apply_filter())

        cols = ("time", "difficulty", "hero", "duration", "bp", "level", "kda", "lh", "gold", "hdmg", "tdmg", "tower")
        # 表格外层 1px 描边 + 双向滚动条：12 列在窄窗口下也能完整查看
        tree_wrap = tk.Frame(right, bg=LINE, padx=1, pady=1)
        tree_wrap.pack(fill="both", expand=True)
        tree_inner = tk.Frame(tree_wrap, bg=PANEL)
        tree_inner.pack(fill="both", expand=True)
        tree_inner.columnconfigure(0, weight=1)
        tree_inner.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_inner, columns=cols, show="headings", height=30)
        headers = (
            ("time", "时间", 148),
            ("difficulty", "难度", 40),
            ("hero", "英雄", 100),
            ("duration", "时长", 52),
            ("bp", "勇士积分", 68),
            ("level", "等级", 34),
            ("kda", "K/D/A", 70),
            ("lh", "补刀", 50),
            ("gold", "金币", 76),
            ("hdmg", "英雄伤害", 80),
            ("tdmg", "承受伤害", 80),
            ("tower", "塔杀", 40),
        )
        self.tree_headers = {col: text for col, text, _ in headers}
        for col, text, w in headers:
            # 表头点击三态循环：升序 → 降序 → 恢复
            self.tree.heading(col, text=text, command=lambda c=col: self._on_sort(c))
            self.tree.column(col, width=w, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self._style_tree(self.tree)

        vsb = ttk.Scrollbar(
            tree_inner, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar"
        )
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(
            tree_inner, orient="horizontal", command=self.tree.xview, style="Dark.Horizontal.TScrollbar"
        )
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    def _build_version_badge(self, parent):
        """右上角版本徽章：当前版本 / 服务器最新版本常驻可见，红点引导手动更新。

        不主动弹任何更新窗口；发现新版本只把徽章变红，用户点徽章才打开
        UpdateWindow。徽章用 tk 控件而非 ttk，便于逐个上色与整体点击。
        """
        self._version_state = "checking"
        self._latest_info = None
        self._badge_hover = False
        self.version_badge = tk.Frame(
            parent, bg=PANEL_SOFT, highlightbackground=LINE,
            highlightthickness=1, cursor="hand2", padx=8, pady=4,
        )
        self.version_badge.pack(side="right", padx=(8, 10))

        self.badge_widgets = []

        # 两行：当前版本 / 最新版本；标签列右对齐、版本号列左对齐，保证上下对齐。
        def mk(text, fg, font=None, row=0, column=0, sticky="w", padx=0, pady=0):
            lab = tk.Label(
                self.version_badge, text=text, fg=fg, bg=PANEL_SOFT,
                font=font or (FONT_UI, 9), bd=0, cursor="hand2",
            )
            lab.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
            self.badge_widgets.append(lab)
            return lab

        mk("当前版本", MUTED, font=(FONT_UI, 9, "bold"), row=0, column=0,
           sticky="e", padx=(0, 6), pady=(0, 2))
        self.lbl_local_version = mk(
            f"v{APP_VERSION}", TEXT, font=(FONT_UI, 10, "bold"),
            row=0, column=1, sticky="w",
        )
        mk("最新版本", MUTED, font=(FONT_UI, 9, "bold"), row=1, column=0,
           sticky="e", padx=(0, 6))
        self.lbl_remote_version = mk(
            "检查中…", MUTED, font=(FONT_UI, 10, "bold"),
            row=1, column=1, sticky="w",
        )
        self.lbl_version_dot = mk(
            " ", DANGER, font=(FONT_UI, 11, "bold"),
            row=1, column=2, sticky="w", padx=(6, 0),
        )
        self.lbl_version_action = mk(
            "", FAINT, font=(FONT_UI, 9, "bold"),
            row=1, column=3, sticky="w", padx=(2, 0),
        )
        # 固定占位宽度：检查完成、亮红点时徽章不忽宽忽窄，顶栏不跳动。
        # 边框厚度也保持恒定，警示只靠红框颜色 + 红点 + 暗红底区分。
        # 两个版本号用相同固定宽度，保证上下两行版本号框等宽、视觉严格对齐
        # （仅给「最新」加宽会让上行偏窄、下行像被缩进；宽度固定也避免状态切换时徽章抖动）。
        self.lbl_local_version.configure(width=8)
        self.lbl_remote_version.configure(width=8)
        self.lbl_version_dot.configure(width=2)
        self.lbl_version_action.configure(width=8)
        self.version_badge.configure(highlightthickness=1)

        for w in (self.version_badge, *self.badge_widgets):
            w.bind("<Button-1>", lambda e: self._on_version_click())
            w.bind("<Enter>", lambda e: self._paint_badge(True))
            w.bind("<Leave>", lambda e: self._paint_badge(False))

    def _paint_badge(self, hover):
        """悬停只换成更亮的深色底，文字保持浅色，绝不出现白底白字。"""
        self._badge_hover = hover
        if self._version_state == "update":
            bg = BADGE_ALERT_HOVER if hover else BADGE_ALERT_BG
        else:
            bg = BTN_HOVER if hover else PANEL_SOFT
        for w in (self.version_badge, *self.badge_widgets):
            w.configure(bg=bg)

    def _set_version_badge(self, state, remote_version=None):
        """主线程更新徽章：checking / latest / update / failed / off。"""
        self._version_state = state
        alert = state == "update"
        self.version_badge.configure(highlightbackground=DANGER if alert else LINE)
        if alert:
            self.lbl_remote_version.configure(text=f"v{remote_version}", fg=DANGER)
            self.lbl_version_dot.configure(text="●")
            self.lbl_version_action.configure(text="点击更新", fg=DANGER)
        else:
            self.lbl_version_dot.configure(text=" ")
            if state == "checking":
                self.lbl_remote_version.configure(text="检查中…", fg=MUTED)
                self.lbl_version_action.configure(text="", fg=FAINT)
            elif state == "failed":
                self.lbl_remote_version.configure(text="未知", fg=FAINT)
                self.lbl_version_action.configure(text="检查失败", fg=FAINT)
            elif state == "off":
                self.lbl_remote_version.configure(text="未检查", fg=FAINT)
                self.lbl_version_action.configure(text="", fg=FAINT)
            else:
                self.lbl_remote_version.configure(
                    text=f"v{remote_version or APP_VERSION}", fg=TEXT
                )
                self.lbl_version_action.configure(text="已是最新", fg=FAINT)
        self._update_version_check_button()
        self._paint_badge(self._badge_hover)

    def _update_version_check_button(self):
        """版本检查失败时才显示「重试检查」按钮，其它状态隐藏（零占位）。"""
        if self._version_state == "failed":
            if self.btn_version_check.winfo_manager() != "pack":
                self.btn_version_check.pack(side="left")
        else:
            if self.btn_version_check.winfo_manager() == "pack":
                self.btn_version_check.pack_forget()

    def _on_manual_version_check(self):
        """手动触发一次服务器版本检查（常用于自动检查失败后的重试）。"""
        if self._closed:
            return
        self.lbl_status.configure(text="正在手动检查服务器版本…")
        self._check_version(show_checking=True)

    def _on_version_click(self):
        """红点徽章是手动更新入口：点开更新窗口，其它状态只给状态栏提示。"""
        if self._closed:
            return
        if self._version_state == "update" and self._latest_info:
            self._show_update_window(self._latest_info)
        elif self._version_state == "checking":
            self.lbl_status.configure(text="正在检查服务器版本，请稍候…")
        elif self._version_state == "failed":
            # 点徽章与「重试检查」按钮同样可触发手动重试
            self._on_manual_version_check()
        else:
            self.lbl_status.configure(
                text=f"当前已是最新版本 v{APP_VERSION}，右上「更新日志」可查看历史更新"
            )

    def _make_selectable(self, label):
        """让 Label 可被鼠标选中并复制 (Ctrl+C)"""
        label.configure(takefocus=True)
        label.bind("<Button-1>", lambda e: self._start_select(label, e))
        label.bind("<B1-Motion>", lambda e: self._extend_select(label, e))
        label.bind("<ButtonRelease-1>", lambda e: self._end_select(label, e))
        label.bind("<Control-c>", lambda e: self._copy_select(label))

    def _start_select(self, label, event):
        label.focus_set()
        try:
            label.selection_range(0, "end")
            label.selection_anchor(0)
            label.icursor("xterm")
        except Exception:
            pass

    def _extend_select(self, label, event):
        try:
            label.icursor("xterm")
            label.selection_range(0, f"@{event.x}")
        except Exception:
            pass

    def _end_select(self, label, event):
        try:
            label.selection_clear()
        except Exception:
            pass

    def _copy_select(self, label):
        try:
            text = label.selection_get()
        except Exception:
            text = label.cget("text")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.lbl_status.config(text=f"已复制: {text}")

    # ================= 会员表 / 勇士表 =================
    def _on_mousewheel(self, event):
        """左列和会员表各自滚动；鼠标在右侧战绩表时不干预"""
        path = str(event.widget)
        step = -3 if event.delta > 0 else 3
        if path == str(self.mem_canvas) or path.startswith(str(self.mem_canvas) + "."):
            self.mem_canvas.yview_scroll(step, "units")
        elif path == str(self.left_canvas) or path.startswith(str(self.left_canvas) + "."):
            self.left_canvas.yview_scroll(step, "units")

    def _toggle_member(self):
        self.member_open = not self.member_open
        if self.member_open:
            self.mem_body.pack(fill="x", pady=(S2, 0), after=self.mem_summary)
            self.mem_toggle.config(text="会员等级预测（未来 100 级）  ▲")
        else:
            self.mem_body.pack_forget()
            self.mem_toggle.config(text="会员等级预测（未来 100 级）  ▼")
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    @staticmethod
    def _num(widget, default=None):
        try:
            return float(widget.get().strip())
        except (ValueError, AttributeError, tk.TclError):
            return default

    def _render_member_table(self):
        """按每天固定会员经验，推算未来 100 级的达成日期；一行 2 个"""
        signature = (
            self.profile.get("memberPointTotal"),
            self._num(self.mem_daily),
            datetime.now().date(),
        )
        if signature == self._mem_signature:
            return  # 自动刷新数据没变就不重建，避免闪烁与滚动跳动
        self._mem_signature = signature
        view = self.mem_canvas.yview()
        for c in self.mem_list.winfo_children():
            c.destroy()
        total = self.profile.get("memberPointTotal") or 0
        cur = level_from_exp(total, MEMBER_STEP, MEMBER_BASE)
        daily = self._num(self.mem_daily)
        if not total or daily is None or daily <= 0:
            self.mem_summary.config(text="当前会员经验未知，或「每日经验」需填写大于 0 的数字")
            return

        today = datetime.now().date()
        items = []
        for i in range(1, 101):
            lv = cur + i
            need = level_cum(lv, MEMBER_STEP, MEMBER_BASE) - total
            days = max(0, math.ceil(need / daily))
            items.append((lv, (today + timedelta(days=days)).strftime("%Y-%m-%d")))

        for r in range(0, 100, 2):
            bg = PANEL if (r // 2) % 2 else PANEL_SOFT
            row = tk.Frame(self.mem_list, bg=bg)
            row.pack(fill="x")
            for j in range(2):
                lv, d = items[r + j]
                cell = tk.Label(
                    row,
                    text=f"{lv}级  {d}",
                    bg=bg,
                    fg=TEXT,
                    font=(FONT_NUM, 11),
                    anchor="w",
                    width=21,
                )
                cell.grid(row=0, column=j, sticky="w", padx=(0, 10))
                self._make_selectable(cell)

        self.mem_canvas.yview_moveto(view[0])
        self.mem_summary.config(
            text=(
                f"当前 {cur} 级 · 总经验 {total:,} · 本级 "
                f"{self.profile.get('memberCurrPoint', 0):,}/{self.profile.get('memberNextPoint', 0):,}"
                f" · 按每天 {daily:g} 经验\n"
                f"{cur + 1}~{cur + 100} 级达成日期（最近一级 {items[0][1]}；仅计每日签到，可在上方修改）"
            )
        )
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _on_self_toggle(self, keep_manual=False):
        """勾选「是自己」→ 起始等级置灰并用自己当前总积分起算；取消 → 置空可填。
        升到等级默认 = 起始等级 +10，方便直接看到预测结果。"""
        own = level_from_exp(self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE)
        self.war_start.configure(state="normal")
        if self.self_var.get():
            self.war_start.delete(0, "end")
            self.war_start.insert(0, str(own))
            self.war_start.configure(state="disabled")
            # 升到等级仅在用户尚未填写时给默认（起始+10），
            # 避免自动刷新每轮覆盖用户已改的值
            if not self.war_target.get().strip():
                self.war_target.delete(0, "end")
                self.war_target.insert(0, str(own + 10))
        elif not keep_manual:
            # 显式取消勾选：清空两个等级框，由用户手动填写
            self.war_start.delete(0, "end")
            self.war_target.delete(0, "end")
        elif not self.war_target.get().strip():
            # 未勾选但保留手动值：升到等级为空时按「起始等级 +10」给默认
            start = self._num(self.war_start)
            if start is not None:
                self.war_target.delete(0, "end")
                self.war_target.insert(0, str(int(start) + 10))
        self._render_warrior()

    def _render_warrior(self):
        p = self.profile
        total = p.get("seasonPointTotal") or 0
        own = level_from_exp(total, WARRIOR_STEP, WARRIOR_BASE)
        self.war_info.config(
            text=(
                f"自己勇士：{own} 级 · 总积分 {total:,} · 本级 "
                f"{p.get('seasonCurrPoint', 0):,}/{p.get('seasonNextPoint', 0):,}"
                f" · 近期场均 {fmt_duration(self.avg_duration)}"
            )
        )

        if self.self_var.get():
            start_level, start_exp = own, total
        else:
            start_level = self._num(self.war_start)
            start_exp = level_cum(int(start_level), WARRIOR_STEP, WARRIOR_BASE) if start_level else None
        target = self._num(self.war_target)
        avg = self._num(self.war_avg)
        gpd = self._num(self.war_games)

        if start_exp is None or target is None or avg is None or gpd is None or avg <= 0 or gpd <= 0:
            self.war_res1.config(text="请填写有效的起始等级 / 升至等级 / 积分 / 每天把数")
            self.war_res2.config(text="")
            self.war_hint.config(text="")
            return

        target = int(target)
        need = level_cum(target, WARRIOR_STEP, WARRIOR_BASE) - start_exp
        if need <= 0:
            self.war_res1.config(text=f"升至等级需高于起始等级（当前按 {start_level:g} 级起算）")
            self.war_res2.config(text="")
            self.war_hint.config(text="")
            return

        games_pure = math.ceil(need / avg)
        hours_pure = games_pure * self.avg_duration / 3600 if self.avg_duration else 0
        daily_pts = gpd * avg + self.task_points
        days = math.ceil(need / daily_pts)
        games_real = max(0, math.ceil((need - days * self.task_points) / avg))
        hours_real = games_real * self.avg_duration / 3600 if self.avg_duration else 0

        self.war_res1.config(
            text=(
                f"需要 {games_pure:,} 局 · 约 {hours_pure:,.1f} 小时"
                f"（纯靠对局，场均 {fmt_duration(self.avg_duration)}）"
            )
        )
        self.war_res2.config(
            text=(
                f"需要 {days:,} 天 · 约 {days / 30.4:.1f} 个月"
                f"（每天 {gpd:g} 把 × {avg:g} + 任务 {self.task_points} = {daily_pts:,.0f} 积分）"
            )
        )
        self.war_hint.config(
            text=(
                f"{start_level:g} 级 → {target} 级 共需 {need:,} 积分；"
                f"计入每天 {self.task_points} 任务奖励后，实际约 {games_real:,} 局 / {hours_real:,.1f} 小时"
                f"（「是自己」时按当前总积分 {total:,} 起算）"
            )
        )

    def _style_tree(self, tree, big=False):
        """配置表格样式。big=True 使用更大字体"""
        style = ttk.Style()
        name = "BigTreeview" if big else "Treeview"
        head = "BigTreeview.Heading" if big else "Treeview.Heading"
        font = (FONT_UI, 11) if big else (FONT_UI, 10)
        rowh = 34 if big else 28

        style.configure(
            name,
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=rowh,
            borderwidth=0,
            relief="flat",
            font=font,
        )
        style.configure(
            head,
            background=PANEL_SOFT,
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            padding=(4, 6),
            font=(FONT_UI, 9, "bold"),
        )
        # 表头悬停用深色高亮 + 强调色文字；选中行蓝底配深色字，避免
        # clam 默认的白字蓝底（#ffffff / #4a6984）对比不足。
        style.map(head, background=[("active", BTN_HOVER)],
                  foreground=[("active", ACCENT)])
        style.map(name, background=[("selected", ACCENT)],
                  foreground=[("selected", BG)])
        if tree is not None:
            tree.tag_configure("odd", background=PANEL, foreground=TEXT)
            tree.tag_configure("even", background=PANEL_SOFT, foreground=TEXT)

    # ================= 手动刷新 / 自动刷新开关 =================
    def refresh(self):
        """手动刷新：立刻启动一组新线程抓数据；本组未结束前重复点击无效。

        不等待 5 秒定时器：若此刻有一组自动轮在途，新组会抢占它（旧组 cancel
        置位、旧结果按 seq 丢弃），保证点击后立刻重新取数。
        """
        if self._closed or self._manual_busy:
            return
        self._begin_fetch(manual=True)

    def _on_auto_toggle(self):
        """勾选才启用 5 秒自动刷新；取消勾选立即取消待触发的定时器。"""
        if self._closed:
            return
        self.ctrl.set_enabled(bool(self.auto_var.get()))

    # ---------- 刷新中特效：只在手动刷新的那组线程在途时显示 ----------
    _SPIN_FRAMES = ("◐", "◓", "◑", "◒")

    def _set_refresh_label(self, text):
        btn = getattr(self, "btn_refresh", None)
        if btn is None or self._closed:
            return
        try:
            btn.config(text=text)
        except Exception:
            pass  # 窗口销毁过程中不再碰控件

    def _start_spin(self):
        self._stop_spin()
        self._spin_active = True
        self._spin_idx = 0
        self._tick_spin()

    def _tick_spin(self):
        if self._closed or not self._spin_active:
            return
        frame = self._SPIN_FRAMES[self._spin_idx % len(self._SPIN_FRAMES)]
        self._spin_idx += 1
        self._set_refresh_label(f"{frame} 刷新中")
        self._spin_timer = self.root.after(FETCH_SPIN_MS, self._tick_spin)

    def _stop_spin(self):
        self._spin_active = False
        if self._spin_timer is not None:
            try:
                self.root.after_cancel(self._spin_timer)
            except Exception:
                pass
            self._spin_timer = None
        self._set_refresh_label("刷新")

    # ================= 窗口关闭 =================
    def _on_close(self):
        self._closed = True
        self._round_cancel.set()  # 在途线程立即退出、不再入队
        self._stop_spin()
        self.ctrl.stop()
        self.root.destroy()

    # ---------- 版本检查与可选更新 ----------
    def start_version_check(self):
        """启动入口调用一次：先把徽章置为「检查中」，再子线程查服务器版本。"""
        self._check_version(show_checking=True)

    def _maybe_refresh_version(self):
        """自动刷新每轮静默顺带查一次版本（带最小间隔节流）。

        不把徽章置为「检查中」，避免每轮闪烁；结果回来才更新。受 checkUpdate
        开关、最小间隔、是否已有检查在途三重保护，不并发、不频繁打扰。
        """
        if self._closed or not self.cfg.get("checkUpdate", 1):
            return
        if self._version_checking:
            return
        if time.monotonic() - self._last_version_check < VERSION_CHECK_MIN_INTERVAL_MS / 1000:
            return
        self._check_version(show_checking=False)

    def _check_version(self, show_checking):
        """发起一次服务器版本检查（子线程）；show_checking 时先把徽章置为检查中。"""
        if self._closed or not self.cfg.get("checkUpdate", 1):
            self._set_version_badge("off")
            return
        if self._version_checking:
            return
        if show_checking:
            self._set_version_badge("checking")
        self._version_checking = True
        self._last_version_check = time.monotonic()
        url = self.cfg.get("versionUrl", VERSION_URL)

        def worker():
            try:
                info, err = fetch_version_info(url), None
            except Exception as e:
                info, err = None, str(e)
            if not self._closed:
                self._updates.put(("version", info, err))

        threading.Thread(target=worker, daemon=True).start()
        self._ensure_update_polling()

    def _ensure_update_polling(self):
        if self._update_polling or self._closed:
            return
        self._update_polling = True
        self._poll_updates()

    def _poll_updates(self):
        """主线程轮询版本/下载事件；所有 Tk 操作都留在这里（R009）。"""
        if self._closed:
            self._update_polling = False
            return
        try:
            kind, payload, extra = self._updates.get_nowait()
        except queue.Empty:
            self.root.after(200, self._poll_updates)
            return
        handler = getattr(self, f"_on_update_{kind}", None)
        if handler:
            handler(payload, extra)
        if self._update_active:
            self.root.after(50, self._poll_updates)
        else:
            self._update_polling = False

    def _on_update_version(self, info, err):
        """只更新右上角徽章：有新版亮红点，绝不主动弹窗打扰用户。

        比对上次写入的版本状态：一致则跳过写入（避免每轮无谓重绘徽章）。
        仅当正在显示「检查中…」时（show_checking 入口）强制落地结果，
        否则徽章会卡在「检查中…」不回落。
        """
        self._update_active = False
        self._version_checking = False
        if err or not info:
            new_state, new_remote = "failed", None
        else:
            self._latest_info = info
            remote = info.get("version")
            new_state, new_remote = (
                "update" if is_newer(remote, APP_VERSION) else "latest", remote,
            )
        if self._version_state != "checking" and \
                self._last_version_state == new_state and \
                self._last_remote_version == new_remote:
            return
        self._last_version_state = new_state
        self._last_remote_version = new_remote
        self._set_version_badge(new_state, new_remote)

    def _show_update_window(self, info):
        """仅由用户点击版本徽章触发；可关闭，不强制更新。"""
        win = self._update_window
        if win is not None and win.winfo_exists():
            return
        self._update_window = UpdateWindow(self.root, self, info)

    def _show_changelog(self):
        win = self._changelog_window
        if win is not None and win.winfo_exists():
            win.lift()
            return
        self._changelog_window = ChangelogWindow(
            self.root, title="更新日志", subtitle=f"当前版本 v{APP_VERSION}", entries=CHANGELOG,
            close_on_focus_out=True, toggle_widget=self.btn_changelog,
        )

    def start_update(self, info, window=None):
        """用户点「立即更新」才触发：后台下载 exe，不阻塞界面。"""
        if self._update_active or self._closed:
            return
        url = (info or {}).get("downloadUrl")
        if not url:
            if window:
                window.set_error("版本清单缺少 downloadUrl")
            return
        # 源码运行没有 exe 可替换，降级为打开下载页手动处理。
        if not getattr(sys, "frozen", False):
            webbrowser.open((info or {}).get("releasePage") or url)
            if window:
                window.set_error("源码运行模式，请在下载页手动替换 exe")
            return
        self._update_active = True
        self._update_window = window or self._update_window
        dest = os.path.join(APP_DIR, UPDATE_NEW_NAME)
        try:
            os.remove(dest)
        except OSError:
            pass
        if window:
            window.set_busy()

        def worker():
            try:
                download_file(
                    url, dest,
                    progress=lambda d, t: self._updates.put(("progress", (d, t), None)),
                )
            except Exception as e:
                self._updates.put(("error", str(e), None))
            else:
                self._updates.put(("done", dest, None))

        threading.Thread(target=worker, daemon=True).start()
        self._ensure_update_polling()

    def _on_update_progress(self, payload, extra):
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_progress(*payload)

    def _on_update_done(self, path, extra):
        self._update_active = False
        self._new_exe = path
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_ready()

    def _on_update_error(self, msg, extra):
        self._update_active = False
        self._new_exe = None
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_error(msg)

    def finish_update(self, window=None):
        """二次确认后写替换脚本并关窗；脚本等进程退出后覆盖 exe 并重启。"""
        if not self._new_exe or not os.path.isfile(self._new_exe):
            return
        try:
            apply_update(self._new_exe)
        except Exception as e:
            if window is not None and window.winfo_exists():
                window.set_error(f"无法启动更新脚本：{e}")
            return
        self._on_close()

    def _begin_fetch(self, manual=False):
        """启动一组取数线程：3 接口各一线程并行，成功即止，失败最多 5 次、间隔 0.5s。

        手动刷新会抢占上一组：旧组 cancel 置位后旧线程快速退出、旧结果按 seq 丢弃，
        新组立即开跑；自动轮若撞上在途的一组则跳过并重排定时器，保证不并发堆叠。
        子线程只入队结果，所有界面操作仍由主线程 _poll_results 完成（R009）。
        """
        if self._closed:
            return
        if manual:
            if self._manual_busy:
                return
        elif self._fetch_busy:
            # 有组在途（多为一组手动刷新）：自动轮不叠加，在途那轮收尾会重排
            self.ctrl.finished()
            return

        self._maybe_refresh_version()

        # 作废旧组，开新组：seq 用于丢弃旧结果，cancel 用于让旧线程立刻退出
        self._round_cancel.set()
        cancel = threading.Event()
        self._round_cancel = cancel
        self._fetch_seq += 1
        seq = self._fetch_seq
        self._fetch_busy = True
        if manual:
            self._manual_busy = True
            self._start_spin()

        self._round = {
            "seq": seq, "ranking": None, "info": None, "recent": None,
            "warnings": [], "failed": set(), "done": 0, "changed": False,
        }
        if not self._rendered_once:
            if not str(self.lbl_status.cget("text")).startswith("用户"):
                self.lbl_status.config(text="正在加载数据...")

        max_attempts = int(self.cfg.get("fetchMaxAttempts", FETCH_MAX_ATTEMPTS))
        retry_s = float(self.cfg.get(
            "fetchRetryIntervalMs", FETCH_RETRY_INTERVAL_S * 1000)) / 1000
        specs = (
            ("ranking", self.fetcher.fetch_ranking, "排行榜"),
            ("info", self.fetcher.fetch_info, "会员/赛季资料"),
            ("recent", self.fetcher.fetch_recent, "近期战绩"),
        )
        threads = []
        self._round_threads = threads

        def worker(k, f, lab):
            """单接口线程：重试到成功或次数用尽；组结束/被抢占即 return，线程随之关闭。"""
            try:
                try:
                    res, err = fetch_with_retry(f, cancel, max_attempts, retry_s)
                except FetchCancelled:
                    return
                if cancel.is_set() or self._closed:
                    return
                self._results.put((k, res, err, lab, seq))
            finally:
                try:
                    threads.remove(threading.current_thread())
                except ValueError:
                    pass

        for key, fn, label in specs:
            t = threading.Thread(
                target=worker, args=(key, fn, label), daemon=True,
                name=f"fetch-{key}-{seq}",
            )
            threads.append(t)
            t.start()
        # 首次轮询也交回事件循环：子线程只入队，主线程异步取回；顺带保证
        # 首轮「正在加载数据...」不会在 _begin_fetch 内被同步清掉。
        self.root.after(20, lambda s=seq: self._poll_results(s))

    def _poll_results(self, seq=None):
        """主线程轮询：一次排空队列，只认当前有效组 seq，旧组结果直接丢弃。"""
        if self._closed:
            return
        if seq is None:
            seq = self._fetch_seq
        if seq != self._fetch_seq or self._round is None:
            return  # 本组已被抢占：停掉这条轮询链，避免两条链重复计数
        while True:
            try:
                key, res, err, label, rseq = self._results.get_nowait()
            except queue.Empty:
                break
            if rseq != seq:
                continue  # 旧组残留结果，丢弃
            r = self._round
            r[key] = res
            if err:
                r["warnings"].append(f"{label} 请求失败（{err.split(':', 1)[0]}）")
                r["failed"].add(label)
            else:
                handler = getattr(self, f"_on_data_{key}", None)
                if handler:
                    handler(res)
            r["done"] += 1
            if r["done"] >= 3:
                self._finish_round()
                return
        self.root.after(20, lambda s=seq: self._poll_results(s))

    # ---------- 各接口独立处理：各自比对、各自更新 ----------
    def _on_data_ranking(self, ranking):
        """排行榜：仅比对排名，变了才更新排名卡（卡片区由 _card_signature 守卫）。"""
        if not isinstance(ranking, dict):
            return
        new_rank = ranking.get("rank", "-")
        if new_rank != self._last_rank:
            self.profile["rank"] = new_rank
            self._last_rank = new_rank
            self._render_cards()
            if self._round is not None:
                self._round["changed"] = True

    def _on_data_info(self, info):
        """会员/赛季资料：字段比对，变了才更新卡片 + 会员表 + 勇士计算。"""
        if not isinstance(info, dict):
            return
        fields = {
            "seasonLevel": info.get("seasonLevel"),
            "seasonNeed": (
                (info.get("seasonNextLevelPoint") or 0) - (info.get("seasonCurrrentLevelPoint") or 0)
                if info.get("seasonLevel") is not None else None
            ),
            "memberLevel": info.get("memberLevel"),
            "memberNeed": (
                (info.get("memberNextLevelPoint") or 0) - (info.get("memberCurrentLevelPoint") or 0)
                if info.get("memberLevel") is not None else None
            ),
            "matchCount": info.get("matchCount"),
            "winCount": info.get("winCount"),
            "memberPointTotal": info.get("memberPointTotal") or 0,
            "memberCurrPoint": info.get("memberCurrentLevelPoint") or 0,
            "memberNextPoint": info.get("memberNextLevelPoint") or 0,
            "seasonPointTotal": info.get("seasonPointTotal") or 0,
            "seasonCurrPoint": info.get("seasonCurrrentLevelPoint") or 0,
            "seasonNextPoint": info.get("seasonNextLevelPoint") or 0,
        }
        if fields != self._last_info_fields:
            self.profile.update(fields)
            self._last_info_fields = fields
            self._render_cards()
            self._render_member_table()
            self._on_self_toggle(keep_manual=True)
            if self._round is not None:
                self._round["changed"] = True

    def _on_data_recent(self, recent):
        """近期战绩：聚合后比对战绩明细与每日统计，变了才重绘战绩表 / 每日统计。"""
        if recent is None:
            return
        rows, days, avg = self.fetcher.derive_rows_days(recent)
        self._apply_recent_data(rows, days, avg)

    def _apply_recent_data(self, rows, days, avg):
        """近期战绩聚合结果的统一落盘：独立比对后只重绘变动区块。"""
        rows_changed = (rows != self.rows)
        days_changed = (days != self.days)
        if rows_changed or days_changed or not self._days_rendered or not self._rows_rendered:
            self.rows = rows
            self.days = days
            self.avg_duration = avg
            if days_changed or not self._days_rendered:
                self._render_days()
                self._days_rendered = True
            if rows_changed or not self._rows_rendered:
                self.apply_filter()
                self._rows_rendered = True
            self._render_member_table()
            self._on_self_toggle(keep_manual=True)
            if self._round is not None:
                self._round["changed"] = True

    def _finish_round(self):
        """一组三接口收齐后的收尾：关掉这组线程状态、恢复按钮，再推进自动刷新。"""
        r = self._round
        self._round = None
        self._fetch_busy = False
        self._round_threads = []
        manual_done = self._manual_busy
        self._manual_busy = False
        if manual_done:
            self._stop_spin()  # 仅手动轮有特效；自动轮完全无感知，不碰按钮与状态栏
        if r is None:
            return
        try:
            # 接口失败保持静默：失败接口保留上一轮旧内容（R034）；首轮清掉
            # 「正在加载数据...」，之后自动轮不动状态栏。
            if not self._rendered_once:
                if not str(self.lbl_status.cget("text")).startswith("用户"):
                    self.lbl_status.config(text="", style="Muted.TLabel")
            # 仅在有接口真正变动时才刷新「更新于」时间戳，避免无变化时跳动
            if r["changed"]:
                self.lbl_updated.config(
                    text=f"更新于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
        finally:
            self._rendered_once = True
            if not self._closed:
                self.ctrl.finished()  # 勾上自动刷新才会安排 5 秒后的下一轮

    def _data_signature(self, data):
        """取展示内容相关的字段做比对；排除 updatedAt 等每次刷新都变的时间戳。"""
        return (
            data.get("profile"),
            data.get("rows"),
            data.get("days"),
            data.get("warnings") or [],
            data.get("failed") or [],
            data.get("avgDurationSec"),
        )

    def _data_unchanged(self, data):
        """所有接口数据与上次写入一致则视为未变：不重绘、不写入界面。"""
        sig = self._data_signature(data)
        if self._last_data_sig is not None and sig == self._last_data_sig:
            return True
        self._last_data_sig = sig
        return False

    def _finish(self, data, err):
        """刷新结束：比对后写入 / 兜底，然后安排下一轮。

        接口失败保持静默（详见 R034）：状态栏不显示失败提示、状态灯不转红，
        失败接口保留旧内容，由自动刷新下一轮重试。
        """
        if self._closed:
            return
        try:
            if data is not None:
                if self._data_unchanged(data):
                    # 数据一致：不重绘界面（不写入），仅清掉首轮加载提示
                    if not self._rendered_once:
                        self.lbl_status.config(text="")
                    self._rendered_once = True
                else:
                    self.render(data)
                    # 首轮渲染成功后清掉「正在加载数据...」提示，不显示失败信息
                    if not self._rendered_once:
                        self.lbl_status.config(text="")
                    self._rendered_once = True
            else:
                # 整轮取数失败：保持静默，状态栏不显示失败提示，等下一轮自动重试
                pass
        except Exception as e:
            self.lbl_status.config(text=f"渲染失败：{e}")
        finally:
            self.ctrl.finished()

    # ---------- 区块渲染：每日统计（仅近期战绩接口成功才重建） ----------
    def _render_days(self):
        for c in self.day_rows_frame.winfo_children():
            c.destroy()
        for idx, d in enumerate(self.days):
            eff = f"{d['eff']:.2f}" if d["eff"] >= 0 else "-"
            cells = (d["date"], d["count"], f"{d['points']:,}", d["time"], eff)
            bg = PANEL if idx % 2 == 0 else PANEL_SOFT
            row = tk.Frame(self.day_rows_frame, bg=bg)
            row.pack(fill="x")
            for i, ((text, w), val) in enumerate(zip(self.day_cols_def, cells)):
                row.columnconfigure(i, minsize=w)
                if text == "效率":
                    fg = DANGER if d["eff"] < 0 else ACCENT  # 只用一种强调色标出关键指标
                else:
                    fg = MUTED if i == 0 else TEXT
                lbl = tk.Label(
                    row,
                    text=str(val),
                    bg=bg,
                    fg=fg,
                    font=(FONT_NUM, 14),
                    anchor="center",
                    pady=5,
                )
                lbl.grid(row=0, column=i, sticky="ew")
                self._make_selectable(lbl)
            tk.Frame(self.day_rows_frame, bg=LINE, height=1).pack(fill="x")

    # ---------- 区块渲染：概览卡片（排行榜/赛季/会员/总场次） ----------
    def _render_cards(self):
        p = self.profile
        sig = (
            p.get("rank"), p.get("seasonLevel"), p.get("seasonNeed"),
            p.get("memberLevel"), p.get("memberNeed"),
            p.get("matchCount"), p.get("winCount"),
        )
        if sig == self._card_signature:
            return  # 数据未变不重绘卡片，避免每轮闪烁
        self._card_signature = sig
        # 4 张卡骨架在 _build_ui 已固定建好，这里只原地更新文字，
        # 副文本行高度始终预留，加载前后高度不变（R040）。
        # 空副文本用空格占位（ttk.Label 空 text 会塌缩到 1px，空格保留整行高度）。
        EMPTY = " "
        s = self._card_slots

        # 0 排行榜排名
        s[0]["value"].config(text=f"{p.get('rank', '-')} 名")
        s[0]["sub_l"].config(text=EMPTY)
        s[0]["sub_r"].config(text=EMPTY)

        # 1 赛季等级
        if p.get("seasonLevel") is not None:
            s[1]["value"].config(text=f"{p['seasonLevel']} 级")
            need = p.get("seasonNeed")
            if need is not None:
                s[1]["sub_l"].config(text=f"距 {p['seasonLevel'] + 1} 级还差 ")
                s[1]["sub_r"].config(text=f"{need:,}")
            else:
                s[1]["sub_l"].config(text=EMPTY)
                s[1]["sub_r"].config(text=EMPTY)
        else:
            s[1]["value"].config(text="— 级")
            s[1]["sub_l"].config(text=EMPTY)
            s[1]["sub_r"].config(text=EMPTY)

        # 2 会员等级
        if p.get("memberLevel") is not None:
            s[2]["value"].config(text=f"{p['memberLevel']} 级")
            need = p.get("memberNeed")
            if need is not None:
                s[2]["sub_l"].config(text=f"距 {p['memberLevel'] + 1} 级还差 ")
                s[2]["sub_r"].config(text=f"{need:,}")
            else:
                s[2]["sub_l"].config(text=EMPTY)
                s[2]["sub_r"].config(text=EMPTY)
        else:
            s[2]["value"].config(text="— 级")
            s[2]["sub_l"].config(text=EMPTY)
            s[2]["sub_r"].config(text=EMPTY)

        # 3 总场次
        if p.get("matchCount"):
            s[3]["value"].config(text=f"{p['matchCount']:,}")
            if p.get("winCount") is not None:
                s[3]["sub_l"].config(text=f"胜率 {p['winCount'] / p['matchCount'] * 100:.1f}%")
            else:
                s[3]["sub_l"].config(text=EMPTY)
            s[3]["sub_r"].config(text=EMPTY)
        else:
            s[3]["value"].config(text="—")
            s[3]["sub_l"].config(text=EMPTY)
            s[3]["sub_r"].config(text=EMPTY)

    def render(self, data):
        """整页渲染入口（测试 / 兜底 / 手动全量刷新用）。

        内部逐接口复用 _on_data_* / _apply_recent_data 的独立比对+更新逻辑，
        与并行刷新路径行为一致：某接口失败则保留上一轮已成功的该区块内容。
        """
        self.lbl_updated.config(text=f"更新于 {data['updatedAt']}")
        # 接口失败保持静默：不写入状态栏、状态灯不转红；失败接口按 failed 集合
        # 跳过对应区块，保留上一轮已成功的旧内容（详见 R034）。

        # 逐接口独立比对、独立更新：失败接口跳过该区块，保留上一轮已成功内容
        failed = set(data.get("failed", []))
        p = data["profile"]
        if "排行榜" not in failed:
            self._on_data_ranking(p)
        if "会员/赛季资料" not in failed:
            self._on_data_info(p)
        if "近期战绩" not in failed:
            self._apply_recent_data(
                data["rows"], data["days"], data.get("avgDurationSec") or 0
            )

        # 勇士目标等级仅在为空时自动预填一次（依赖会员/赛季经验）
        if not self.war_target.get().strip():
            self.war_target.insert(
                0,
                str(level_from_exp(
                    self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE) + 10),
            )
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _update_headings(self):
        """表头排序标记：当前排序列显示方向箭头 ▲/▼（醒目且随点击切换），
        并在表头提示条同步高亮当前排序；未排序时提示可点击排序。"""
        for col, text in self.tree_headers.items():
            mark = ""
            if col == self.sort_col and self.sort_state:
                mark = " ▲" if self.sort_state == 1 else " ▼"
            self.tree.heading(col, text=text + mark)
        # 表头提示条：随排序状态变化，醒目高亮当前排序；未排序时仅作可点击提示
        if self.sort_col and self.sort_state:
            arrow = "▲" if self.sort_state == 1 else "▼"
            self.lbl_sort_hint.configure(
                text=f"排序：{self.tree_headers[self.sort_col]} {arrow}",
                style="SortActive.TLabel",
            )
        else:
            self.lbl_sort_hint.configure(text="点击可排序", style="Chip.TLabel")

    def _on_sort(self, col):
        """点击表头三态循环：升序 → 降序 → 恢复原始顺序；换列从升序开始。"""
        if self.sort_col == col:
            self.sort_state = (self.sort_state + 1) % 3
        else:
            self.sort_col, self.sort_state = col, 1
        if self.sort_state == 0:
            self.sort_col = None
        self._update_headings()
        self.apply_filter()

    def apply_filter(self):
        q = self.search.get().strip().lower()
        rows = [r for r in self.rows if not q or q in r["hero"].lower()]
        if self.sort_col and self.sort_state:
            rows.sort(key=SORT_KEYS[self.sort_col], reverse=self.sort_state == 2)

        view = self.tree.yview()
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(rows):
            hero = r["hero"] + ("  [觉醒]" if r["awaken"] else "") + ("  [掉线]" if r["disconnected"] else "")
            tag = "even" if i % 2 else "odd"
            self.tree.insert(
                "",
                "end",
                values=(
                    r["time"],
                    r["difficulty"],
                    hero,
                    r["durationText"],
                    f"+{r['battlePoints']}",
                    r["level"],
                    f"{r['kills']}/{r['deaths']}/{r['assists']}",
                    f"{r['lastHits']:,}",
                    f"{r['gold']:,}",
                    f"{r['heroDamage']:,}",
                    f"{r['damageTaken']:,}",
                    r["towerKills"],
                ),
                tags=(tag,),
            )
        # 重建后恢复原来的滚动位置，刷新 / 排序不把列表弹回顶部
        if view and view != (0.0, 1.0) and self.tree.get_children():
            self.tree.yview_moveto(view[0])


def main():
    root = tk.Tk()
    try:
        # 高 DPI 适配
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App(root)
    app.start_version_check()
    root.mainloop()


if __name__ == "__main__":
    main()
