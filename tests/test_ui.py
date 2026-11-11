"""近期战绩三态排序 + 无感知自动刷新的 GUI 行为测试（隐藏窗口，离线）。"""

import inspect
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import app as A  # noqa: E402

CFG = {
    "userId": "129175832",
    "refreshToken": "RT",
    "tzOffset": 8,
    "gameDayStartHour": 8,
    "taskPoints": 300,
    "autoRefreshIntervalMs": 30,
}
HEROES = {"nevermore": "影魔"}

PROFILE = {
    "rank": 12,
    "seasonLevel": 71,
    "seasonNeed": 7100,
    "memberLevel": 20,
    "memberNeed": 1950,
    "matchCount": 100,
    "winCount": 55,
    "memberPointTotal": 28100,
    "memberCurrPoint": 550,
    "memberNextPoint": 2500,
    "seasonPointTotal": 251711,
    "seasonCurrPoint": 3211,
    "seasonNextPoint": 10311,
}


def make_row(hero="甲", bp=100, level=50, gold=1000, sec=1200, difficulty="N3",
             kills=1, deaths=2, assists=3):
    return {
        "time": "2026-11-11 10:00:00",
        "difficulty": difficulty,
        "hero": hero,
        "awaken": False,
        "disconnected": False,
        "win": True,
        "durationText": A.fmt_duration(sec),
        "durationSec": sec,
        "battlePoints": bp,
        "level": level,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "lastHits": 10,
        "gold": gold,
        "heroDamage": 500,
        "damageTaken": 300,
        "towerKills": 1,
    }


def make_data(rows, warnings=None):
    return {
        "profile": dict(PROFILE),
        "days": [],
        "rows": rows,
        "avgDurationSec": 1500,
        "warnings": list(warnings or []),
        "updatedAt": "2026-11-11 11:00:00",
    }


class TestGuiBehaviour(unittest.TestCase):
    def setUp(self):
        self.root = A.tk.Tk()
        self.root.withdraw()
        with mock.patch.object(
            A, "load_json", side_effect=lambda name: dict(CFG) if name == "config.json" else HEROES
        ):
            self.app = A.App(self.root)
        self.app.fetcher.collect = lambda: make_data([])

    def tearDown(self):
        self.app._on_close()

    def col_values(self, index):
        return [self.app.tree.item(i, "values")[index] for i in self.app.tree.get_children()]

    def bp_values(self):
        return self.col_values(4)

    def gold_values(self):
        return self.col_values(8)

    # ---------- 三态排序 ----------
    def test_tri_state_asc_desc_restore(self):
        self.app.rows = [make_row("甲", 300), make_row("乙", 100), make_row("丙", 200)]
        self.app.apply_filter()
        self.assertEqual(self.bp_values(), ["+300", "+100", "+200"], "初始为接口原始顺序")

        self.app._on_sort("bp")
        self.assertEqual(self.bp_values(), ["+100", "+200", "+300"])
        self.assertIn("▲", self.app.tree.heading("bp", "text"))

        self.app._on_sort("bp")
        self.assertEqual(self.bp_values(), ["+300", "+200", "+100"])
        self.assertIn("▼", self.app.tree.heading("bp", "text"))

        self.app._on_sort("bp")
        self.assertEqual(self.bp_values(), ["+300", "+100", "+200"], "第三次点击恢复原始顺序")
        self.assertEqual(self.app.tree.heading("bp", "text"), "勇士积分")
        self.assertIsNone(self.app.sort_col)
        self.assertEqual(self.app.sort_state, 0)

        self.app._on_sort("bp")
        self.assertEqual(self.app.sort_state, 1, "恢复后再点重新从升序开始")

    def test_switch_column_restarts_ascending(self):
        self.app.rows = [make_row(gold=900), make_row(gold=10000), make_row(gold=2000)]
        self.app._on_sort("bp")
        self.app._on_sort("bp")
        self.assertEqual(self.app.sort_state, 2)
        self.app._on_sort("gold")
        self.assertEqual(self.app.sort_col, "gold")
        self.assertEqual(self.app.sort_state, 1)
        self.assertEqual(self.app.tree.heading("bp", "text"), "勇士积分")
        self.assertIn("▲", self.app.tree.heading("gold", "text"))

    def test_numeric_sort_not_display_string(self):
        self.app.rows = [make_row(gold=900), make_row(gold=10000), make_row(gold=2000)]
        self.app._on_sort("gold")
        self.assertEqual(self.gold_values(), ["900", "2,000", "10,000"])

    def test_duration_and_difficulty_keys(self):
        self.assertEqual(A.SORT_KEYS["duration"](make_row(sec=90)), 90)
        self.assertEqual(A.SORT_KEYS["difficulty"]({"difficulty": "N3"}), (0, 3))
        self.assertEqual(A.SORT_KEYS["difficulty"]({"difficulty": "自定义"}), (1, 0))
        self.assertGreater(
            A.SORT_KEYS["kda"]({"kills": 10, "deaths": 1, "assists": 0}),
            A.SORT_KEYS["kda"]({"kills": 2, "deaths": 5, "assists": 1}),
        )

    def test_sort_combined_with_search(self):
        self.app.rows = [make_row("影魔", 300), make_row("影魔", 100), make_row("其他", 200)]
        self.app.search.insert(0, "影魔")
        self.app._on_sort("bp")
        self.assertEqual(self.bp_values(), ["+100", "+300"])

    def test_sort_survives_auto_refresh(self):
        rows = [make_row("甲", 300), make_row("乙", 100), make_row("丙", 200)]
        self.app.render(make_data(rows))
        self.app._on_sort("bp")
        self.assertEqual(self.bp_values(), ["+100", "+200", "+300"])
        ids_before = list(self.app.tree.get_children())

        self.app.render(make_data(rows))  # 模拟 5 秒后的自动刷新，数据未变
        self.assertEqual(self.bp_values(), ["+100", "+200", "+300"])
        self.assertEqual(list(self.app.tree.get_children()), ids_before, "数据未变不应重建表格行")

    # ---------- 无感知刷新 ----------
    def test_no_wait_cursor_anywhere(self):
        src = (
            inspect.getsource(A.App._begin_fetch)
            + inspect.getsource(A.App._finish)
            + inspect.getsource(A.App.render)
        )
        self.assertNotIn('cursor="watch"', src, "自动刷新不得把鼠标改成等待形状")
        self.assertNotIn("cursor=", src)

        cursor_before = self.root.cget("cursor")
        self.app._finish(make_data([]), None)  # 首轮
        self.app.lbl_status.config(text="用户提示保留")
        self.app._begin_fetch()
        self.assertEqual(self.root.cget("cursor"), cursor_before)
        self.assertEqual(self.app.lbl_status.cget("text"), "用户提示保留",
                         "自动刷新不应显示加载文字或清掉用户提示")

    def test_manual_refresh_still_gives_feedback(self):
        self.app._finish(make_data([]), None)
        with mock.patch.object(self.app.ctrl, "_start_refresh", lambda: None):
            self.app.refresh()
        self.assertEqual(self.app.lbl_status.cget("text"), "正在加载数据...")
        self.assertTrue(self.app._manual_pending)

    def test_error_visible_then_cleared_on_success(self):
        self.app._finish(make_data([], warnings=["/stats/recent 请求失败（TimeoutError）"]), None)
        self.assertIn("部分接口失败", self.app.lbl_status.cget("text"))
        self.app._finish(make_data([]), None)
        self.assertEqual(self.app.lbl_status.cget("text"), "")

    def test_scroll_position_restored_after_rebuild(self):
        self.app.rows = [make_row(bp=i) for i in range(30)]
        self.app.apply_filter()
        with mock.patch.object(self.app.tree, "yview", return_value=(0.4, 0.7)), mock.patch.object(
            self.app.tree, "yview_moveto"
        ) as moveto:
            self.app.apply_filter()
            moveto.assert_called_once_with(0.4)

    def test_member_table_not_rebuilt_when_unchanged(self):
        self.app.render(make_data([]))
        ids_before = [str(c) for c in self.app.mem_list.winfo_children()]
        self.assertTrue(ids_before)
        self.app.render(make_data([]))
        self.assertEqual([str(c) for c in self.app.mem_list.winfo_children()], ids_before)


if __name__ == "__main__":
    unittest.main()
