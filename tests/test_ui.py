"""近期战绩三态排序 + 无感知自动刷新的 GUI 行为测试（隐藏窗口，离线）。"""

import inspect
import os
import shutil
import sys
import tempfile
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


def _luminance(color):
    """相对亮度：用来验证「深色底 + 浅色字」，不写死具体色值。"""
    color = str(color).lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


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
        self.tmpdir = tempfile.mkdtemp(prefix="dota-ui-test-")
        cfg = dict(CFG, dbPath=os.path.join(self.tmpdir, "ui.db"))
        with mock.patch.object(
            A, "load_json", side_effect=lambda name: dict(cfg) if name == "config.json" else HEROES
        ):
            self.app = A.App(self.root)
        # 每个接口独立线程取数：mock 掉三个 fetch 方法，避免测试里真联网
        self.app.fetcher.fetch_ranking = lambda: {"rank": 12}
        self.app.fetcher.fetch_info = lambda: dict(PROFILE)
        self.app.fetcher.fetch_recent = lambda: {"matches": []}
        self.app.fetcher.collect = lambda: make_data([])  # 兼容直接调用 collect 的测试

    def tearDown(self):
        self.app._on_close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def col_values(self, index):
        return [self.app.tree.item(i, "values")[index] for i in self.app.tree.get_children()]

    def bp_values(self):
        return self.col_values(4)

    def gold_values(self):
        return self.col_values(8)

    # ---------- 深色主题悬停对比度 ----------
    def test_clam_button_states_are_dark_bg_light_fg(self):
        style = A.ttk.Style()
        for name in ("TButton", "Update.TButton"):
            mapping = style.map(name)
            bg = dict(mapping.get("background", []))
            fg = dict(mapping.get("foreground", []))
            for state in ("active", "pressed"):
                self.assertIn(state, bg, f"{name} 缺 {state} 背景映射，会用 clam 近白底")
                self.assertIn(state, fg, f"{name} 缺 {state} 前景映射，会白底白字")
                self.assertLess(_luminance(bg[state]), 0.2, f"{name} {state} 底必须是深色")
                self.assertGreater(_luminance(fg[state]), 0.5, f"{name} {state} 字必须是浅色")
        self.assertNotEqual(
            dict(style.map("TButton").get("background", [])).get("active"), "#eeebe7",
            "回归：clam 默认 active 背景 #eeebe7 就是近白色",
        )

    def test_tree_heading_and_selection_keep_contrast(self):
        style = A.ttk.Style()
        head = style.map("Treeview.Heading")
        self.assertIn("active", dict(head.get("foreground", [])), "表头悬停也要指定前景")
        self.assertLess(_luminance(dict(head["background"])["active"]), 0.2)
        self.assertGreater(_luminance(dict(head["foreground"])["active"]), 0.3)
        sel = dict(style.map("Treeview").get("foreground", []))
        self.assertEqual(str(sel.get("selected")), A.BG,
                         "蓝底选中行配深色字，不用 clam 默认白字")

    # ---------- 标题提示与三态排序 ----------
    def test_recent_section_hint_is_click_to_sort(self):
        self.assertEqual(str(self.app.lbl_sort_hint.cget("text")), "点击可排序")
        self.assertNotIn("最近", str(self.app.lbl_sort_hint.cget("text")))
        self.app.render(make_data([make_row("甲"), make_row("乙")]))
        self.assertEqual(str(self.app.lbl_sort_hint.cget("text")), "点击可排序",
                         "提示固定，不再随战绩行数变成 (最近 N 场)")

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

    # ---------- 变更比对：一致则不写入 ----------
    def test_render_skipped_when_data_unchanged(self):
        d = make_data([])
        self.app._finish(d, None)  # 首轮：写入并建立基线
        with mock.patch.object(self.app, "render") as render:
            self.app._finish(d, None)  # 相同数据：应跳过重绘（不写入界面）
            render.assert_not_called()

    def test_render_runs_when_data_changed(self):
        self.app._finish(make_data([]), None)
        with mock.patch.object(self.app, "render") as render:
            self.app._finish(make_data([make_row(bp=999)]), None)  # 战绩变了
            render.assert_called_once()

    def _days_payload(self, count):
        d = make_data([])
        d["days"] = [{"date": "11-12", "count": count, "points": 300,
                      "time": "1:00:00", "eff": 5.0}]
        return d

    def test_daily_stats_not_rebuilt_when_unchanged(self):
        d = self._days_payload(3)
        self.app.render(d)  # 首次：_days_rendered=False -> 必须重建建基线
        with mock.patch.object(self.app, "_render_days") as rd:
            self.app.render(d)  # 每日统计聚合结果没变 -> 跳过重绘
            rd.assert_not_called()

    def test_daily_stats_rebuilt_when_changed(self):
        self.app.render(self._days_payload(3))
        with mock.patch.object(self.app, "_render_days") as rd:
            self.app.render(self._days_payload(4))  # 聚合结果变了 -> 必须重绘
            rd.assert_called_once()

    def test_daily_stats_renders_all_columns_per_row(self):
        """回归：每行必须生成全部 5 列标签，不能因缩进错误只生成效率单列。"""
        data = make_data([])
        data["days"] = [
            {"date": "11-12", "count": 3, "points": 900, "time": "2时3分", "eff": 480.23},
            {"date": "11-11", "count": 2, "points": 600, "time": "1时30分", "eff": 411.21},
        ]
        self.app.render(data)
        rows = [w for w in self.app.day_rows_frame.winfo_children()
                if isinstance(w, A.tk.Frame)
                and any(isinstance(c, A.tk.Label) for c in w.winfo_children())]
        self.assertEqual(len(rows), 2, "应有 2 行每日统计")
        for row in rows:
            labels = [w for w in row.winfo_children() if isinstance(w, A.tk.Label)]
            self.assertEqual(
                len(labels), len(self.app.day_cols_def),
                f"每行应生成 {len(self.app.day_cols_def)} 个单元格，实际 {len(labels)}",
            )
            # 首列（日期）与末列（效率）都应有实际文字，不能空白
            self.assertTrue(labels[0].cget("text"), "日期列不应空白")
            self.assertTrue(labels[-1].cget("text"), "效率列不应空白")

    def test_version_badge_not_rewritten_when_unchanged(self):
        info = {"version": A.APP_VERSION, "downloadUrl": "u", "releasePage": "p"}
        self.app._on_update_version(info, None)  # 首次写入
        with mock.patch.object(self.app, "_set_version_badge") as setter:
            self.app._on_update_version(info, None)  # 相同结果且非检查中
            setter.assert_not_called()

    def test_version_badge_rewritten_on_change(self):
        self.app._on_update_version({"version": A.APP_VERSION}, None)  # 已是最新
        with mock.patch.object(self.app, "_set_version_badge") as setter:
            self.app._on_update_version({"version": "9.9.9"}, None)  # 出现新版本
            setter.assert_called_once()

    def test_first_load_shows_and_clears_loading_feedback(self):
        # 刷新按钮已移除：仅首轮加载显示「正在加载数据...」，渲染完成后清空；
        # 之后自动刷新无感知、不再显示加载文字（详见 R010 / R039）。
        self.app._begin_fetch()
        self.assertEqual(self.app.lbl_status.cget("text"), "正在加载数据...")
        self.app._finish(make_data([]), None)
        self.assertEqual(self.app.lbl_status.cget("text"), "")

    def test_interface_failure_not_shown_in_status(self):
        # 接口失败保持静默（R034）：状态栏不出现「部分接口失败」等失败提示
        self.app._finish(make_data([], warnings=["/stats/recent 请求失败（TimeoutError）"]), None)
        self.assertNotIn("部分接口失败", self.app.lbl_status.cget("text"))
        self.assertNotIn("失败", self.app.lbl_status.cget("text"))
        # 成功刷新后状态栏仍为空，不残留失败提示
        self.app._finish(make_data([]), None)
        self.assertEqual(self.app.lbl_status.cget("text"), "")

    def test_sort_hint_highlights_active_sort(self):
        # 排序中：提示条切换为强调色并标明当前排序列与方向（醒目、随点击变化）
        self.app.rows = [make_row("甲", 300), make_row("乙", 100)]
        self.app._on_sort("bp")
        self.assertIn("排序：", str(self.app.lbl_sort_hint.cget("text")))
        self.assertIn("▲", str(self.app.lbl_sort_hint.cget("text")))
        self.assertEqual(str(self.app.lbl_sort_hint.cget("style")), "SortActive.TLabel")
        # 恢复原始顺序后回到中性「点击可排序」提示
        self.app._on_sort("bp")
        self.app._on_sort("bp")
        self.assertEqual(str(self.app.lbl_sort_hint.cget("text")), "点击可排序")
        self.assertEqual(str(self.app.lbl_sort_hint.cget("style")), "Chip.TLabel")

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

    # ---------- 手动刷新按钮 / 自动刷新开关 / 刷新中特效 ----------
    def test_refresh_button_present_and_auto_unchecked_by_default(self):
        self.assertTrue(self.app.btn_refresh.winfo_exists())
        self.assertEqual(str(self.app.btn_refresh.cget("text")), "刷新")
        self.assertEqual(self.app.auto_var.get(), 0, "自动刷新默认不勾")
        self.assertFalse(self.app.ctrl.enabled)
        self.assertEqual(str(self.app.auto_chk.cget("text")), "自动刷新")
        self.assertEqual(int(self.app.btn_refresh.cget("width")), 10,
                         "按钮宽度固定，切换刷新中文字时顶栏不跳动")

    def test_toggle_auto_refresh_enables_and_disables_timer(self):
        self.assertIsNone(self.app.ctrl._timer)
        self.app.auto_var.set(1)
        self.app._on_auto_toggle()
        self.assertTrue(self.app.ctrl.enabled)
        self.assertIsNotNone(self.app.ctrl._timer, "勾上应立刻排一轮")
        self.app.auto_var.set(0)
        self.app._on_auto_toggle()
        self.assertFalse(self.app.ctrl.enabled)
        self.assertIsNone(self.app.ctrl._timer, "取消勾选应撤掉待触发定时器")

    def test_manual_refresh_spins_and_blocks_repeat_clicks(self):
        self.app.refresh()
        self.assertTrue(self.app._manual_busy)
        self.assertTrue(self.app._spin_active)
        self.assertIn("刷新中", str(self.app.btn_refresh.cget("text")))
        seq = self.app._fetch_seq
        self.app.refresh()  # 这组线程未结束，重复点击无效
        self.assertEqual(self.app._fetch_seq, seq, "不得再起一组线程")
        self.app._finish_round()  # 模拟这组三个接口全部收齐
        self.assertFalse(self.app._manual_busy)
        self.assertFalse(self.app._spin_active)
        self.assertEqual(str(self.app.btn_refresh.cget("text")), "刷新")

    def test_auto_round_has_no_spin_effect(self):
        self.app._begin_fetch(manual=False)
        self.assertFalse(self.app._spin_active, "自动轮保持无感知，不显示刷新中特效")
        self.assertEqual(str(self.app.btn_refresh.cget("text")), "刷新")
        self.app._finish_round()

    def test_default_unchecked_does_not_schedule_next_round(self):
        self.app._begin_fetch(manual=False)
        self.app._finish_round()
        self.assertIsNone(self.app.ctrl._timer, "默认不勾：取完一轮就停，不轮询")

    def test_manual_refresh_preempts_in_flight_round(self):
        self.app._begin_fetch(manual=False)
        old_seq = self.app._fetch_seq
        old_cancel = self.app._round_cancel
        self.app.refresh()  # 立刻起新组，不等 5 秒定时器
        self.assertGreater(self.app._fetch_seq, old_seq)
        self.assertTrue(old_cancel.is_set(), "旧组应被取消，线程快速退出")
        self.assertTrue(self.app._manual_busy)
        # 旧组迟到的结果按 seq 丢弃，不得计入当前组
        for t in list(self.app._round_threads):
            t.join(timeout=1)
        while not self.app._results.empty():
            self.app._results.get_nowait()
        self.app._results.put(("ranking", {"rank": 999}, None, "排行榜", old_seq))
        self.app._poll_results(self.app._fetch_seq)
        self.assertEqual(self.app._round["done"], 0)
        self.assertNotEqual(self.app.profile["rank"], 999)

    def test_failed_interface_keeps_old_content(self):
        """逐接口独立更新：某接口失败时不覆盖上一轮已成功的区块内容。"""
        ok = make_data([make_row("甲", 300)])
        self.app.render(ok)  # 成功一轮：填满排行榜/赛季/会员/总场次
        old_season = self.app.profile["seasonLevel"]
        old_member = self.app.profile["memberLevel"]
        old_match = self.app.profile["matchCount"]
        self.assertEqual(len(self.app.cards_frame.winfo_children()), 4, "成功时四张卡片齐全")

        # 模拟「会员/赛季资料」接口失败：数据解析为空，并标记 failed
        bad = make_data([make_row("甲", 300)],
                        warnings=["会员/赛季资料 请求失败（TimeoutError）"])
        bad["failed"] = ["会员/赛季资料"]
        bad["profile"] = {k: None for k in PROFILE}
        bad["profile"]["rank"] = 12  # 排行榜接口未失败，新数据有效
        self.app.render(bad)

        # 失败接口的字段必须保留上一轮旧内容，不更新
        self.assertEqual(self.app.profile["seasonLevel"], old_season)
        self.assertEqual(self.app.profile["memberLevel"], old_member)
        self.assertEqual(self.app.profile["matchCount"], old_match)
        self.assertEqual(len(self.app.cards_frame.winfo_children()), 4, "失败接口不删卡片，旧内容保留")
        # 未失败的排行榜接口正常刷新
        self.assertEqual(self.app.profile["rank"], 12)

    def test_all_interfaces_failed_keeps_everything(self):
        """三个接口全失败时，所有区块保持上一轮旧内容，不闪烁清空。"""
        ok = make_data([make_row("甲", 300)])
        self.app.render(ok)
        before = dict(self.app.profile)
        before_rows = list(self.app.rows)

        all_bad = make_data([make_row("甲", 300)], warnings=["a", "b", "c"])
        all_bad["failed"] = ["排行榜", "会员/赛季资料", "近期战绩"]
        all_bad["profile"] = {k: None for k in PROFILE}
        all_bad["profile"]["rank"] = "-"
        all_bad["rows"] = []
        all_bad["days"] = []
        self.app.render(all_bad)

        self.assertEqual(self.app.profile, before, "全失败时 profile 不变")
        self.assertEqual(self.app.rows, before_rows, "全失败时战绩表不变")


class TestAutoRefreshPersistence(unittest.TestCase):
    """自动刷新开关跨重启：用同一个本地库反复重建 App 模拟关掉 exe 再打开。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dota-pref-test-")
        self.db_path = os.path.join(self.tmpdir, "pref.db")
        self.root = None
        self.app = None
        self.cfg = dict(CFG, dbPath=self.db_path)
        self._new_app()

    def _new_app(self, **overrides):
        """销毁旧实例后用同一个 dbPath 重新构造（等价于重新打开 exe）。"""
        if self.app is not None:
            self.app._on_close()
            self.app = None
        elif self.root is not None:
            self.root.destroy()
        self.root = A.tk.Tk()
        self.root.withdraw()
        cfg = dict(self.cfg, **overrides)
        with mock.patch.object(
            A, "load_json",
            side_effect=lambda name: dict(cfg) if name == "config.json" else HEROES,
        ):
            self.app = A.App(self.root)
        self.app.fetcher.fetch_ranking = lambda: {"rank": 12}
        self.app.fetcher.fetch_info = lambda: dict(PROFILE)
        self.app.fetcher.fetch_recent = lambda: {"matches": []}

    def tearDown(self):
        if self.app is not None:
            self.app._on_close()
        elif self.root is not None:
            self.root.destroy()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def saved(self):
        return A.storage.get_meta(self.db_path, A.PREF_AUTO_REFRESH, None)

    def test_no_saved_pref_uses_config_default(self):
        self.assertEqual(self.app.auto_var.get(), 0)
        self.assertFalse(self.app.ctrl.enabled)
        self.assertIsNone(self.saved(), "从未点过开关不应写库，避免锁死 config 默认值")
        self._new_app(autoRefresh=1)
        self.assertEqual(self.app.auto_var.get(), 1, "没存过时 config.autoRefresh=1 仍是默认")
        self.assertTrue(self.app.ctrl.enabled)

    def test_checkbox_click_persists_on_state_across_restart(self):
        self.app.auto_chk.invoke()  # 真实点一下小勾：切变量 + 触发 command
        self.assertEqual(self.app.auto_var.get(), 1)
        self.assertTrue(self.app.ctrl.enabled)
        self.assertEqual(self.saved(), "1")
        self._new_app()
        self.assertEqual(self.app.auto_var.get(), 1, "重启后必须仍是开启")
        self.assertTrue(self.app.ctrl.enabled, "重启后继续自动刷新")

    def test_uncheck_overrides_config_default_after_restart(self):
        self.app.auto_chk.invoke()   # 先开
        self.app.auto_chk.invoke()   # 再关
        self.assertEqual(self.saved(), "0")
        self._new_app(autoRefresh=1)
        self.assertEqual(self.app.auto_var.get(), 0, "用户关过就以用户选择为准")
        self.assertFalse(self.app.ctrl.enabled)
        self.assertIsNone(self.app.ctrl._timer, "关闭态不得排自动轮定时器")

    def test_last_choice_wins_after_multiple_toggles(self):
        for _ in range(3):
            self.app.auto_chk.invoke()
        self.assertEqual(self.app.auto_var.get(), 1)
        self._new_app()
        self.assertEqual(self.app.auto_var.get(), 1)
        self.app.auto_chk.invoke()
        self._new_app()
        self.assertEqual(self.app.auto_var.get(), 0, "最后一次选择生效")

    def test_write_failure_does_not_break_toggle(self):
        with mock.patch.object(A.storage, "set_meta", side_effect=OSError("disk full")):
            self.app.auto_chk.invoke()
        self.assertTrue(self.app.ctrl.enabled, "写库失败不能影响本次开关是否生效")
        self._new_app()
        self.assertEqual(self.app.auto_var.get(), 0, "没能落盘时回落到 config 默认值")


if __name__ == "__main__":
    unittest.main()
