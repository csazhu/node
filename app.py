"""10v10AI 数据面板 - 原生 Windows 窗口版"""

import json
import math
import os
import sys
import threading
import urllib.request
import urllib.parse
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


def http_json(url, method="GET", headers=None, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with _opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_id_token(refresh_token):
    data = http_json(
        TOKEN_URL,
        method="POST",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    return data["id_token"]


def api_get(token, url):
    return http_json(url, headers={"Authorization": f"Bearer {token}"})


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

    def collect(self):
        cfg = self.cfg
        token = refresh_id_token(cfg["refreshToken"])

        def get(path):
            try:
                return api_get(token, API_BASE + path)
            except Exception:
                return None

        ranking = get(f"/api/player/{cfg['userId']}/ranking") or {}
        info = get(f"/api/player/{cfg['userId']}/info?include=member") or {}
        recent = get(f"/api/player/{cfg['userId']}/stats/recent") or {}
        matches = recent if isinstance(recent, list) else (recent.get("matches") or [])

        durations = [int(m.get("durationSec") or 0) for m in matches if m.get("durationSec")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        tz = timezone(timedelta(hours=cfg.get("tzOffset", 8)))
        start_hour = cfg.get("gameDayStartHour", 8)
        task_points = cfg.get("taskPoints", 300)

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

        profile = {
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
        return {
            "profile": profile,
            "days": days,
            "rows": rows,
            "avgDurationSec": avg_duration,
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# ================= 界面 =================
BG = "#0d1117"
PANEL = "#161b22"
PANEL_SOFT = "#1c2128"
LINE = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
FAINT = "#6e7681"
ACCENT = "#58a6ff"
SUCCESS = "#3fb950"
DANGER = "#f85149"
GOLD = "#d29922"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("10v10AI 数据面板")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG)
        self.rows = []
        self.filtered = []
        self.profile = {}
        self.avg_duration = 0
        self.member_open = True

        self.cfg = load_json("config.json")
        self.task_points = self.cfg.get("taskPoints", 300)
        self.heroes = load_json("heroes.json")
        self.fetcher = DataFetcher(self.cfg, self.heroes)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("Head.TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("CardLabel.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("CardValue.TLabel", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("CardSub.TLabel", background=PANEL, foreground=FAINT, font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Day.TFrame", background=BG)
        style.configure("DayHead.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("DayCell.TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 13))
        style.configure("DayCellNeg.TLabel", background=BG, foreground=DANGER, font=("Microsoft YaHei UI", 13))
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertbackground=TEXT)
        style.configure("TButton", background=PANEL_SOFT, foreground=TEXT, borderwidth=0, padding=(14, 6))
        style.configure("Soft.TFrame", background=PANEL_SOFT)
        style.configure("Soft.TLabel", background=PANEL_SOFT, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        style.configure("SoftMuted.TLabel", background=PANEL_SOFT, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("SoftHead.TLabel", background=PANEL_SOFT, foreground=ACCENT, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("SoftValue.TLabel", background=PANEL_SOFT, foreground=GOLD, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Dark.Vertical.TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, relief="flat")
        style.map("TEntry", fieldbackground=[("disabled", PANEL_SOFT)], foreground=[("disabled", FAINT)])

        # 先配置好两种表格样式，再创建控件
        self._style_tree(None, big=False)
        self._style_tree(None, big=True)

        top = ttk.Frame(self.root, style="Dark.TFrame")
        top.pack(fill="x", padx=14, pady=(12, 8))
        ttk.Label(top, text="10v10AI 数据面板", style="Head.TLabel").pack(side="left")
        self.lbl_updated = ttk.Label(top, text="", style="Muted.TLabel")
        self.lbl_updated.pack(side="left", padx=(10, 0))
        ttk.Button(top, text="刷新", command=self.refresh).pack(side="right")

        # 概览卡片
        self.cards_frame = ttk.Frame(self.root, style="Dark.TFrame")
        self.cards_frame.pack(fill="x", padx=14, pady=(0, 10))
        for i in range(4):
            self.cards_frame.columnconfigure(i, weight=1, uniform="card")

        # 主体：左（每日统计 / 会员表 / 勇士表）/ 右战绩
        body = ttk.Frame(self.root, style="Dark.TFrame")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        body.columnconfigure(0, minsize=496)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左列整体可滚动，新增面板不会把窗口撑爆
        left_outer = ttk.Frame(body, style="Dark.TFrame")
        left_outer.grid(row=0, column=0, sticky="nsew")
        self.left_canvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0, width=480)
        left_sb = ttk.Scrollbar(
            left_outer, orient="vertical", command=self.left_canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side="right", fill="y")
        self.left_canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(self.left_canvas, style="Dark.TFrame")
        self._left_win = self.left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfig(self._left_win, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        ttk.Label(left, text="每日统计", style="Section.TLabel").pack(anchor="w", pady=(0, 6))

        day_wrap = ttk.Frame(left, style="Dark.TFrame")
        day_wrap.pack(fill="x")

        # 每日统计用 grid 布局，表头与内容严格对齐
        self.day_cols_def = (("日期", 110), ("场次", 70), ("积分", 95), ("总耗时", 85), ("效率", 85))
        head_row = ttk.Frame(day_wrap, style="Day.TFrame")
        head_row.pack(fill="x", pady=(0, 4))
        for i, (text, w) in enumerate(self.day_cols_def):
            head_row.columnconfigure(i, minsize=w)
            tk.Label(
                head_row,
                text=text,
                bg=BG,
                fg=MUTED,
                font=("Microsoft YaHei UI", 11, "bold"),
                anchor="center",
            ).grid(row=0, column=i, sticky="ew")

        self.day_rows_frame = ttk.Frame(day_wrap, style="Dark.TFrame")
        self.day_rows_frame.pack(fill="x")

        # ---------- 会员表：未来 100 级达成日期（一行 2 个，可折叠下拉 + 内部滚动） ----------
        mem_box = ttk.Frame(left, style="Soft.TFrame", padding=(10, 8))
        mem_box.pack(fill="x", pady=(10, 0))
        mem_head = ttk.Frame(mem_box, style="Soft.TFrame")
        mem_head.pack(fill="x")
        self.mem_toggle = tk.Button(
            mem_head,
            text="会员等级预测（未来 100 级）  ▲",
            command=self._toggle_member,
            bg=PANEL_SOFT,
            fg=ACCENT,
            activebackground=LINE,
            activeforeground=ACCENT,
            font=("Microsoft YaHei UI", 11, "bold"),
            bd=0,
            relief="flat",
            anchor="w",
            cursor="hand2",
        )
        self.mem_toggle.pack(side="left")
        ttk.Label(mem_head, text="每日", style="SoftMuted.TLabel").pack(side="left", padx=(12, 2))
        self.mem_daily = ttk.Entry(mem_head, width=6, justify="center")
        self.mem_daily.insert(0, "100")
        self.mem_daily.pack(side="left")
        self.mem_daily.bind("<KeyRelease>", lambda e: self._render_member_table())
        ttk.Label(mem_head, text="经验", style="SoftMuted.TLabel").pack(side="left", padx=(3, 0))

        self.mem_summary = ttk.Label(mem_box, text="", style="SoftMuted.TLabel", wraplength=430)
        self.mem_summary.pack(anchor="w", pady=(6, 0))

        self.mem_body = ttk.Frame(mem_box, style="Soft.TFrame")
        self.mem_body.pack(fill="x", pady=(8, 0), after=self.mem_summary)
        self.mem_canvas = tk.Canvas(self.mem_body, bg=PANEL_SOFT, highlightthickness=0, height=120)
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
        war_box = ttk.Frame(left, style="Soft.TFrame", padding=(10, 6))
        war_box.pack(fill="x", pady=(8, 0))
        ttk.Label(war_box, text="勇士等级计算（1000 起每级 +100）", style="SoftHead.TLabel").pack(anchor="w")
        self.war_info = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=430)
        self.war_info.pack(anchor="w", pady=(4, 6))

        grid = ttk.Frame(war_box, style="Soft.TFrame")
        grid.pack(fill="x")

        def add_war_row(r, label, default):
            ttk.Label(grid, text=label, style="Soft.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            e = ttk.Entry(grid, width=10, justify="center")
            e.grid(row=r, column=1, sticky="w", padx=(8, 0))
            if default:
                e.insert(0, default)
            e.bind("<KeyRelease>", lambda ev: self._render_warrior())
            return e

        self.war_start = add_war_row(0, "起始等级", "")
        self.self_var = tk.IntVar(value=1)
        self.self_chk = tk.Checkbutton(
            grid,
            text="是否是自己",
            variable=self.self_var,
            command=self._on_self_toggle,
            bg=PANEL_SOFT,
            fg=TEXT,
            selectcolor=PANEL,
            activebackground=PANEL_SOFT,
            activeforeground=TEXT,
            bd=0,
            highlightthickness=0,
            font=("Microsoft YaHei UI", 10),
        )
        self.self_chk.grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.war_target = add_war_row(1, "升至等级", "")
        self.war_avg = add_war_row(2, "平均每把积分", "105")
        self.war_games = add_war_row(3, "一天打多少把", "10")

        self.war_res1 = ttk.Label(war_box, text="—", style="SoftValue.TLabel", wraplength=430)
        self.war_res1.pack(anchor="w", pady=(8, 2))
        self.war_res2 = ttk.Label(war_box, text="—", style="SoftValue.TLabel", wraplength=430)
        self.war_res2.pack(anchor="w", pady=(0, 2))
        self.war_hint = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=430)
        self.war_hint.pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(body, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))

        bar = ttk.Frame(right, style="Dark.TFrame")
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="近期战绩", style="Section.TLabel").pack(side="left")
        self.lbl_match_count = ttk.Label(bar, text="", style="Muted.TLabel")
        self.lbl_match_count.pack(side="left", padx=(8, 0))
        ttk.Label(bar, text="输入英雄名搜索", style="Muted.TLabel").pack(side="right", padx=(8, 4))
        self.search = ttk.Entry(bar, width=20)
        self.search.pack(side="right")
        self.search.insert(0, "")
        self.search.bind("<KeyRelease>", lambda e: self.apply_filter())

        cols = ("time", "difficulty", "hero", "duration", "bp", "level", "kda", "lh", "gold", "hdmg", "tdmg", "tower")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=30)
        headers = (
            ("time", "时间", 145),
            ("difficulty", "难度", 55),
            ("hero", "英雄", 110),
            ("duration", "时长", 60),
            ("bp", "勇士积分", 80),
            ("level", "等级", 50),
            ("kda", "K/D/A", 85),
            ("lh", "补刀", 60),
            ("gold", "金币", 90),
            ("hdmg", "英雄伤害", 95),
            ("tdmg", "承受伤害", 95),
            ("tower", "塔杀", 50),
        )
        for col, text, w in headers:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self._style_tree(self.tree)

        # 滚动条
        sb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        self.lbl_status = ttk.Label(self.root, text="正在加载...", style="Muted.TLabel")
        self.lbl_status.pack(anchor="w", padx=14, pady=(0, 8))

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
            self.mem_body.pack(fill="x", pady=(8, 0), after=self.mem_summary)
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
                    font=("Consolas", 11),
                    anchor="w",
                    width=21,
                )
                cell.grid(row=0, column=j, sticky="w", padx=(0, 10))
                self._make_selectable(cell)

        self.mem_canvas.yview_moveto(0)
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
        """勾选「是自己」→ 起始等级置灰并用自己当前总积分起算；取消 → 置空可填"""
        own = level_from_exp(self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE)
        self.war_start.configure(state="normal")
        if self.self_var.get():
            self.war_start.delete(0, "end")
            self.war_start.insert(0, str(own))
            self.war_start.configure(state="disabled")
        elif not keep_manual:
            self.war_start.delete(0, "end")
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
        font = ("Microsoft YaHei UI", 12) if big else ("Microsoft YaHei UI", 9)
        rowh = 32 if big else 24

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
            font=font,
        )
        style.map(head, background=[("active", PANEL_SOFT)])
        style.map(name, background=[("selected", ACCENT)])
        if tree is not None:
            tree.tag_configure("odd", background=PANEL, foreground=TEXT)
            tree.tag_configure("even", background=PANEL_SOFT, foreground=TEXT)

    def refresh(self):
        self.lbl_status.config(text="正在加载数据...")
        self.root.config(cursor="watch")

        def worker():
            try:
                data = self.fetcher.collect()
                self.root.after(0, lambda: self.render(data))
            except Exception as e:
                self.root.after(0, lambda: self.lbl_status.config(text=f"加载失败: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def render(self, data):
        self.lbl_updated.config(text=f"更新于 {data['updatedAt']}")
        self.lbl_status.config(text="")
        self.root.config(cursor="")
        self.profile = data["profile"]
        self.avg_duration = data.get("avgDurationSec") or 0

        # 卡片
        for c in self.cards_frame.winfo_children():
            c.destroy()
        p = data["profile"]
        cards = [("排行榜排名", f"{p['rank']} 名", "")]
        if p["seasonLevel"] is not None:
            cards.append(
                (
                    "赛季等级",
                    f"{p['seasonLevel']} 级",
                    f"距 {p['seasonLevel'] + 1} 级还差 {p['seasonNeed']:,}" if p["seasonNeed"] is not None else "",
                )
            )
        if p["memberLevel"] is not None:
            cards.append(
                (
                    "会员等级",
                    f"{p['memberLevel']} 级",
                    f"距 {p['memberLevel'] + 1} 级还差 {p['memberNeed']:,}" if p["memberNeed"] is not None else "",
                )
            )
        if p["matchCount"]:
            wr = f"胜率 {p['winCount'] / p['matchCount'] * 100:.1f}%" if p["winCount"] is not None else ""
            cards.append(("总场次", f"{p['matchCount']:,}", wr))
        for i, (label, value, sub) in enumerate(cards):
            f = ttk.Frame(self.cards_frame, style="Card.TFrame", padding=(14, 10))
            f.grid(row=0, column=i, padx=(0, 10), sticky="nsew")
            ttk.Label(f, text=label, style="CardLabel.TLabel").pack(anchor="w")
            ttk.Label(f, text=value, style="CardValue.TLabel").pack(anchor="w")
            if sub:
                ttk.Label(f, text=sub, style="CardSub.TLabel").pack(anchor="w")

        # 每日统计（Label 自绘）
        for c in self.day_rows_frame.winfo_children():
            c.destroy()
        for d in data["days"]:
            eff = f"{d['eff']:.2f}" if d["eff"] >= 0 else "-"
            cells = (d["date"], d["count"], f"{d['points']:,}", d["time"], eff)
            row = ttk.Frame(self.day_rows_frame, style="Dark.TFrame")
            row.pack(fill="x", pady=3)
            for i, ((text, w), val) in enumerate(zip(self.day_cols_def, cells)):
                row.columnconfigure(i, minsize=w)
                style_name = "DayCell.TLabel"
                if text == "效率" and d["eff"] < 0:
                    style_name = "DayCellNeg.TLabel"
                lbl = tk.Label(
                    row,
                    text=str(val),
                    bg=BG,
                    fg=DANGER if style_name == "DayCellNeg.TLabel" else TEXT,
                    font=("Microsoft YaHei UI", 13),
                    anchor="center",
                )
                lbl.grid(row=0, column=i, sticky="ew")
                self._make_selectable(lbl)

        # 战绩
        self.rows = data["rows"]
        self.lbl_match_count.config(text=f"(最近 {len(self.rows)} 场)")
        self.apply_filter()

        # 会员表 / 勇士表
        self._render_member_table()
        if not self.war_target.get().strip():
            self.war_target.insert(0, str(level_from_exp(self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE) + 10))
        self._on_self_toggle(keep_manual=True)
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def apply_filter(self):
        q = self.search.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            if q and q not in r["hero"].lower():
                continue
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


def main():
    root = tk.Tk()
    try:
        # 高 DPI 适配
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
