"""App 主类：组合各职责 Mixin，负责状态初始化与关窗收尾。"""

import json
import queue
import threading
import time
import storage
import tkinter as tk
from .config import APP_DIR, APP_VERSION, AUTO_REFRESH_INTERVAL_MS, load_json
from .network import DataFetcher, RefreshController, configure_proxy
from .theme import BG
from .updater import is_newer
from .ui_build import UIBuildMixin
from .ui_fetch import UIFetchMixin
from .ui_render import UIRenderMixin
from .ui_sync import UISyncMixin
from .ui_version import UIVersionMixin


class App(UIBuildMixin, UIFetchMixin, UIRenderMixin, UISyncMixin, UIVersionMixin):
    """主窗口：由各职责 Mixin 组合，状态与生命周期在此初始化。"""
    def __init__(self, root):
        self.root = root
        self.root.title("10v10AI 数据面板")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG)
        self.rows = []
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
        # 最佳战绩 tab：独立的难度筛选与排序状态
        self.best_tree_headers = {}
        self.best_sort_col = None
        self.best_sort_state = 0
        self.heroes_list = []
        # 英雄筛选两阶段：输入框文本只用来收窄下拉候选，只有从下拉「选中」的值
        # 才写入 hero_selected 并真正筛选列表（recent=近期 / best=最佳），
        # 这样排序 / 难度切换 / 自动刷新不会被半输入的搜索词误筛。
        self.hero_selected = {"recent": "全部英雄", "best": "全部英雄"}
        # 输入链路：中文输入法合成结束不派发 <KeyRelease>，只有 textvariable 的
        # write trace 能可靠捕获文本变化；程序内部写输入框时用 guard 抑制 trace。
        self._hero_trace_guard = False
        self._hero_popdown_jobs = {"recent": None, "best": None}
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
        # 代理写进 config.json：启动即按配置重建 opener，直接双击 exe 也能走代理
        configure_proxy(self.cfg)
        self.task_points = self.cfg.get("taskPoints", 300)
        self.heroes = load_json("heroes.json")
        self.fetcher = DataFetcher(self.cfg, self.heroes)
        # 本地战绩库：接口只负责写库，界面（每日/每月统计、战绩表）只读库
        self.uid = str(self.cfg["userId"])
        self.tz_offset = int(self.cfg.get("tzOffset", 8))
        self.day_start_hour = int(self.cfg.get("gameDayStartHour", 8))
        self.db_path = storage.resolve_db_path(self.cfg, APP_DIR)
        storage.init_db(self.db_path)
        self.months = []
        self._months_rendered = False
        self._last_db_sig = None
        # 每日/每月统计表头筛选（按日期前缀）；默认「全部」即展示全部历史
        self.day_filter_var = tk.StringVar(value="全部")
        self.month_filter_var = tk.StringVar(value="全部")
        self._day_filter = "全部"
        self._month_filter = "全部"
        self._day_filter_cands = []
        self._month_filter_cands = []
        # 每日/每月统计表头排序：0=原始顺序 / 1=升序 / 2=降序，与战绩表三态同款；
        # 排序状态跨筛选与自动刷新保持
        self.day_sort_col = None
        self.day_sort_state = 0
        self.month_sort_col = None
        self.month_sort_state = 0
        # 全量同步：独立结果队列，子线程只入队，主线程轮询更新进度条（R009）
        self._sync_results = queue.Queue()
        self._sync_active = False
        self._sync_cancel = threading.Event()
        self._sync_window = None
        self._sync_polling = False

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
        # 自动刷新默认不开启；以本地库里用户上次的选择为准，
        # 库里没记过（首次运行 / 删库）才回落到 config.json 的 autoRefresh 默认值。
        auto_on = self._load_auto_refresh_pref()
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
        # 启动即把上一轮缓存的接口数据与版本号从库回填界面：先渲染历史，再联网刷新，
        # 之后刷新只改库、有变化才重绘，保证打开 exe 后界面数据全部来自 SQLite。
        self._load_from_db()
        # 启动即取第一轮，延迟到事件循环（避免构造期同步起线程）。这一轮不经过
        # ctrl.request()，所以默认不勾时收尾也不会安排下一轮；勾上则由 ctrl 续跑。
        self.root.after(0, self._begin_fetch)

    # ================= 窗口关闭 =================
    def _on_close(self):
        self._closed = True
        self._round_cancel.set()  # 在途线程立即退出、不再入队
        self._sync_cancel.set()   # 全量同步线程也立即收手
        self._stop_spin()
        self.ctrl.stop()
        if self._sync_window is not None:
            try:
                self._sync_window.destroy()
            except Exception:
                pass
            self._sync_window = None
        self.root.destroy()

    # ================= 启动从库回填（SQLite 单一数据源） =================
    def _load_from_db(self):
        """打开 exe 后先把上一轮缓存的接口数据与版本号回填界面。

        之后无论是主动刷新还是被动刷新，都走「写库 → 按变化重绘」：这里只负责
        在联网之前让界面立刻有内容，断网也能看到上次的数据。
        """
        try:
            rank_raw = storage.load_snapshot(self.db_path, self.uid, "ranking")
            if rank_raw:
                ranking = json.loads(rank_raw)
                self.profile["rank"] = ranking.get("rank", "-")
                self._last_rank = self.profile["rank"]
            info_raw = storage.load_snapshot(self.db_path, self.uid, "info")
            if info_raw:
                info = json.loads(info_raw)
                fields = self._info_fields(info)
                self.profile.update(fields)
                self._last_info_fields = fields
            self._render_cards()
            self._render_member_table()
            self._on_self_toggle(keep_manual=True)
        except Exception:
            pass
        # 战绩 / 每日 / 每月统计：读库渲染（与刷新路径共用的 _refresh_from_db）
        try:
            self._refresh_from_db(force=True)
        except Exception:
            pass
        # 版本徽章：读库回填上次已知版本，联网检查回来再校正
        try:
            ver_raw = storage.load_snapshot(self.db_path, "*", "version")
            if ver_raw:
                info = json.loads(ver_raw)
                self._latest_info = info
                remote = info.get("version")
                state = "update" if is_newer(remote, APP_VERSION) else "latest"
                self._last_version_state = state
                self._last_remote_version = remote
                self._set_version_badge(state, remote)
            # 无缓存版本时保持徽章初始「检查中…」状态，待启动版本检查校正
        except Exception:
            pass
