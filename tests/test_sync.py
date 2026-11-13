"""全量同步窗口 + 接口写库 / 界面读库 的 GUI 行为测试（隐藏窗口、离线）。"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import app as A  # noqa: E402
import storage  # noqa: E402

CFG = {
    "userId": "129175832",
    "refreshToken": "RT",
    "tzOffset": 8,
    "gameDayStartHour": 8,
    "taskPoints": 300,
    "checkUpdate": 0,          # 测试禁止真联网查版本
}
HEROES = {"phantom_assassin": "幻影刺客"}


def m(utc, bp=105, sec=1200):
    return {
        "matchId": "0", "endedAt": utc, "durationSec": sec, "battlePoints": bp,
        "win": True, "heroName": "npc_dota_hero_phantom_assassin", "difficulty": 8,
        "level": 50, "awaken": 1, "isDisconnected": False,
        "kills": 10, "deaths": 0, "assists": 0, "lastHits": 100,
        "heroDamage": 1000, "damageTaken": 500, "towerKills": 1,
        "totalGoldEarned": 1000,
    }


class TestSyncFeature(unittest.TestCase):
    def setUp(self):
        self.root = A.tk.Tk()
        self.root.withdraw()
        self.tmpdir = tempfile.mkdtemp(prefix="dota-sync-test-")
        cfg = dict(CFG, dbPath=os.path.join(self.tmpdir, "sync.db"))
        with mock.patch.object(
            A, "load_json", side_effect=lambda name: dict(cfg) if name == "config.json" else HEROES
        ):
            self.app = A.App(self.root)
        # 全部取数离线化，避免测试真联网
        self.app.fetcher.fetch_ranking = lambda: {"rank": 12}
        self.app.fetcher.fetch_info = lambda: {"seasonLevel": 71}
        self.app.fetcher.fetch_recent = lambda: {"matches": []}
        self.app.fetcher.fetch_history = lambda page=None: {"matches": [], "nextPage": None}

    def tearDown(self):
        self.app._on_close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def pump(self, cond, timeout=4.0):
        """驱动真实事件循环，等子线程结果被主线程轮询消费。"""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if cond():
                return
            time.sleep(0.01)
        self.fail("等待异步流程超时")

    # ---------- UI 结构 ----------
    def test_sync_button_tabs_fixed_height_and_dropdown(self):
        self.assertEqual(str(self.app.btn_sync.cget("text")), "同步")
        tabs = [self.app.stats_nb.tab(t, "text") for t in self.app.stats_nb.tabs()]
        self.assertEqual(tabs, ["每日统计", "每月统计"])
        self.assertEqual(int(self.app.day_canvas.cget("height")), 300,
                         "每日统计固定预留 10 行高度")
        self.assertEqual(int(self.app.month_canvas.cget("height")), 300)
        self.assertFalse(hasattr(self.app, "day_range"), "每日统计范围下拉框已移除")
        rec_tabs = [self.app.rec_nb.tab(t, "text") for t in self.app.rec_nb.tabs()]
        self.assertEqual(rec_tabs, ["近期战绩", "最佳战绩"], "右侧新增最佳战绩 tab")

    def test_sync_window_progress_done_and_retry_states(self):
        self.app._show_sync_window()
        w = self.app._sync_window
        self.assertIsNotNone(w)
        self.assertEqual(str(w.btn_sync.cget("text")), "全量同步历史对局")
        self.app._show_sync_window()  # 重复点击复用同一窗口
        self.assertIs(self.app._sync_window, w)

        w.set_busy()
        self.assertEqual(str(w.btn_sync.cget("state")), "disabled")
        w.set_progress(1, 3, "已同步 1/3 页 · 新增 5 场")
        self.assertIn("1/3", str(w.lbl_state.cget("text")))
        w.set_done(5, 230)
        self.assertIn("同步完成", str(w.lbl_state.cget("text")))
        self.assertIn("230", str(w.lbl_state.cget("text")))
        self.assertEqual(str(w.btn_sync.cget("text")), "全量同步历史对局")
        w.set_error("网络错误")
        self.assertEqual(str(w.btn_sync.cget("text")), "重新同步")
        self.assertIn("同步失败", str(w.lbl_state.cget("text")))
        w.destroy()
        self.assertIsNone(self.app._sync_window)

    # ---------- 全量同步 ----------
    def test_full_sync_writes_all_pages_and_ui_reads_db(self):
        pages = {
            None: {"matches": [m("2026-11-04T14:00:00.000Z"),
                               m("2026-11-03T14:00:00.000Z")], "nextPage": 2},
            2: {"matches": [m("2026-11-02T14:00:00.000Z"),
                            m("2026-11-01T14:00:00.000Z")], "nextPage": 1},
            1: {"matches": [m("2026-10-31T14:00:00.000Z")], "nextPage": None},
        }
        self.app.fetcher.fetch_recent = lambda: {"matches": [m("2026-11-05T14:00:00.000Z")]}
        self.app.fetcher.fetch_history = lambda page=None: pages[page]
        self.app._show_sync_window()
        self.app._start_full_sync()
        self.pump(lambda: not self.app._sync_active)
        self.assertEqual(storage.count_matches(self.app.db_path, self.app.uid), 6)
        self.assertIn("同步完成", str(self.app._sync_window.lbl_state.cget("text")))
        self.assertEqual(len(self.app.tree.get_children()), 6,
                         "同步完成后战绩表必须直接读库拿到全部 6 场")
        self.assertEqual(len(self.app.months), 2, "每月统计按 10/11 两个月聚合")

    def test_full_sync_is_idempotent(self):
        payload = {"matches": [m("2026-11-04T14:00:00.000Z")], "nextPage": None}
        self.app.fetcher.fetch_history = lambda p=None: payload
        for _ in range(2):
            self.app._show_sync_window()
            self.app._start_full_sync()
            self.pump(lambda: not self.app._sync_active)
        self.assertEqual(storage.count_matches(self.app.db_path, self.app.uid), 1,
                         "重复同步不能产生重复对局")

    def test_full_sync_failure_offers_retry(self):
        def boom(page=None):
            raise RuntimeError("连接失败")

        self.app.fetcher.fetch_history = boom
        self.app._show_sync_window()
        self.app._start_full_sync()
        self.pump(lambda: not self.app._sync_active)
        w = self.app._sync_window
        self.assertEqual(str(w.btn_sync.cget("text")), "重新同步")
        self.assertIn("同步失败", str(w.lbl_state.cget("text")))
        self.assertIn("连接失败", str(w.lbl_state.cget("text")))

    # ---------- recent 异步写库，界面只读库 ----------
    def test_recent_writes_db_async_and_ui_reads_db(self):
        ms = [m("2026-11-04T14:00:00.000Z"),
              m("2026-11-04T10:00:00.000Z"),
              m("2026-10-20T10:00:00.000Z")]
        self.app.fetcher.fetch_recent = lambda: {"matches": ms}
        self.app._begin_fetch(manual=True)
        self.pump(lambda: storage.count_matches(self.app.db_path, self.app.uid) == 3
                  and len(self.app.tree.get_children()) == 3)
        self.assertEqual(len(self.app.days), 2, "每日统计来自 DB（11-04 / 10-20）")
        self.assertEqual(len(self.app.months), 2, "每月统计来自 DB（11 / 10）")
        self.assertEqual(self.app._last_db_sig, (3, "2026-11-04T14:00:00.000Z"))

    def test_daily_stats_shows_all_history(self):
        ms = [m(f"2026-11-{d:02d}T12:00:00.000Z") for d in range(1, 13)]
        storage.upsert_matches(self.app.db_path, self.app.uid, ms, 8, 8)
        self.app._refresh_from_db(force=True)
        self.assertEqual(len(self.app.days), 12, "去掉范围下拉框后每日统计展示全部历史")


if __name__ == "__main__":
    unittest.main()
