"""版本检查、可选自动更新与更新日志的离线单元测试（隐藏窗口，不联网、不覆盖 exe）。"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import tkinter.ttk as ttk

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
}
HEROES = {"nevermore": "影魔"}

REMOTE = {
    "version": "1.2.0",
    "downloadUrl": "https://example.invalid/dota-stats.exe",
    "releasePage": "https://example.invalid/releases/latest",
    "changelog": [
        {"version": "1.2.0", "date": "2026-11-12", "items": ["新功能 A", "修复 B"]},
        {"version": "1.1.0", "date": "2026-11-11", "items": ["上一版内容"]},
    ],
}


class FakeResp:
    """假的 HTTP 响应，支持 with / headers / 分块 read。"""

    def __init__(self, chunks, length=None):
        self.chunks = list(chunks)
        self.headers = {
            "Content-Length": str(length if length is not None else sum(len(c) for c in chunks))
        }
        self._i = 0
        self.read_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        self.read_calls.append(n)
        if n is None:
            data = b"".join(self.chunks[self._i:])
            self._i = len(self.chunks)
            return data
        if self._i >= len(self.chunks):
            return b""
        chunk = self.chunks[self._i]
        self._i += 1
        return chunk


def find_text_widget(parent, text):
    """在控件树里按 cget('text') 找控件（ttk.Frame 没 text，跳过）。"""
    for w in parent.winfo_children():
        try:
            if str(w.cget("text")) == text:
                return w
        except Exception:
            pass
        found = find_text_widget(w, text)
        if found is not None:
            return found
    return None


class TestVersionLogic(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(A.version_tuple("v1.2.3"), (1, 2, 3))
        self.assertEqual(A.version_tuple("1.2"), (1, 2))
        self.assertEqual(A.version_tuple("2.0.1-beta4"), (2, 0, 1, 4))
        self.assertEqual(A.version_tuple(None), (0,))
        self.assertEqual(A.version_tuple("abc"), (0,))

    def test_is_newer(self):
        self.assertTrue(A.is_newer("1.2.0", "1.1.0"))
        self.assertTrue(A.is_newer("v1.1.1", "1.1.0"))
        self.assertFalse(A.is_newer("1.1.0", "1.1.0"), "同版本不提示")
        self.assertFalse(A.is_newer("1.1", "1.1.0"), "补 0 后相等")
        self.assertFalse(A.is_newer("1.0.9", "1.1.0"), "更旧不提示")
        self.assertFalse(A.is_newer(None, "1.1.0"))

    def test_new_changelog_entries_only_newer_sorted_desc(self):
        info = {"changelog": [
            {"version": "1.1.0", "items": ["旧"]},
            {"version": "1.3.0", "items": ["最新"]},
            {"version": "1.2.0", "items": ["次新"]},
            {"version": "1.0.0", "items": ["很旧"]},
        ]}
        got = A.new_changelog_entries(info, "1.1.0")
        self.assertEqual([e["version"] for e in got], ["1.3.0", "1.2.0"])
        self.assertEqual(A.new_changelog_entries({}, "1.1.0"), [])

    def test_version_json_matches_builtin_changelog(self):
        with open(os.path.join(ROOT, "version.json"), "r", encoding="utf-8") as f:
            info = json.load(f)
        self.assertEqual(info["version"], A.APP_VERSION, "服务器版本与当前客户端一致，不应弹更新")
        self.assertIn("downloadUrl", info)
        self.assertIn("releasePage", info)
        self.assertEqual(
            [e["version"] for e in info["changelog"]],
            [e["version"] for e in A.CHANGELOG],
            "服务器 changelog 与本地内置更新日志保持一致",
        )

    def test_fetch_version_info_from_local_file(self):
        path = os.path.join(ROOT, "version.json")
        self.assertEqual(A.fetch_version_info(path)["version"], A.APP_VERSION)
        self.assertEqual(A.fetch_version_info("file://" + path)["version"], A.APP_VERSION)

    def test_fetch_version_info_from_http(self):
        with mock.patch.object(A, "http_json", return_value=REMOTE) as hj:
            self.assertEqual(A.fetch_version_info(A.VERSION_URL), REMOTE)
        self.assertEqual(hj.call_args.kwargs["timeout"], A.VERSION_TIMEOUT)
        self.assertGreaterEqual(A.VERSION_TIMEOUT, 10.0, "冷启动首请求实测约 5.2s，需留足余量")

    def test_download_file_writes_exe_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "new.exe")
            progress = []
            with mock.patch.object(A._opener, "open", return_value=FakeResp([b"MZ", b"payload"])):
                A.download_file("https://example.invalid/x", dest,
                                progress=lambda a, b: progress.append((a, b)))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"MZpayload")
            self.assertEqual(progress[-1], (9, 9))

    def test_download_reads_body_in_one_call(self):
        """经代理逐块 read 会把 9 MB 拖到数分钟，必须一次性读取响应体（回归）。"""
        resp = FakeResp([b"MZ", b"a" * 100, b"b" * 50])
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "new.exe")
            with mock.patch.object(A._opener, "open", return_value=resp):
                A.download_file("https://example.invalid/x", dest)
            self.assertEqual(resp.read_calls, [None])
            self.assertEqual(os.path.getsize(dest), 152)

    def test_download_file_rejects_html_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "new.exe")
            with mock.patch.object(A._opener, "open", return_value=FakeResp([b"<html>404</html>"])):
                with self.assertRaises(ValueError):
                    A.download_file("https://example.invalid/x", dest)
            self.assertFalse(os.path.exists(dest), "非 exe 内容必须删除，不能留下坏包")

    def test_build_update_bat_is_ascii_and_self_contained(self):
        bat = A.build_update_bat(4321, "dota-stats.exe", "dota-stats.new.exe")
        bat.encode("ascii")  # 中文目录下也不会乱码
        self.assertIn("set PID=4321", bat)
        self.assertIn('cd /d "%~dp0"', bat)
        self.assertIn('move /Y "%NEW%" "%TARGET%"', bat)
        self.assertIn('start "" "%TARGET%"', bat)
        self.assertIn('del "%~f0"', bat)
        self.assertIn(":wait", bat)

    def test_apply_update_writes_bat_and_launches_once(self):
        with tempfile.TemporaryDirectory() as d:
            new = os.path.join(d, A.UPDATE_NEW_NAME)
            with open(new, "wb") as f:
                f.write(b"MZ")
            with mock.patch.object(A, "APP_DIR", d), \
                 mock.patch.object(A.subprocess, "Popen") as popen:
                bat = A.apply_update(new, os.path.join(d, A.UPDATE_EXE_NAME), pid=4321)
            with open(bat, "r", encoding="ascii") as f:
                self.assertIn("set PID=4321", f.read())
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(popen.call_args.kwargs["cwd"], d)
            self.assertEqual(popen.call_args.args[0][0], "cmd.exe")


class TestChangelogLayout(unittest.TestCase):
    def test_metrics_adapt_to_content(self):
        short = [{"version": "1.2.0", "items": ["短说明"]}]
        height, need_scroll = A._changelog_metrics(short)
        self.assertGreaterEqual(height, 5)
        self.assertLessEqual(height, 8)
        self.assertFalse(need_scroll, "内容少时不应出现滚动条")
        long = [{"version": str(i), "items": ["很长的内容" * 20 for _ in range(3)]}
                for i in range(8)]
        height2, need_scroll2 = A._changelog_metrics(long)
        self.assertEqual(height2, A.CHANGELOG_MAX_LINES)
        self.assertTrue(need_scroll2, "内容多时才限高并启用滚动条")

    def test_lines_keep_version_date_and_items(self):
        rows = A._changelog_lines([{"version": "1.2.0", "date": "2026-11-11",
                                    "items": ["新功能 A", "修复 B"]}])
        self.assertEqual(rows[0], ("version", "v1.2.0", "2026-11-11"))
        self.assertEqual([r[1] for r in rows if r[0] == "item"], ["新功能 A", "修复 B"])
        self.assertEqual(A._changelog_lines([]), [("item", "暂无更新内容")])


class TestVersionGui(unittest.TestCase):
    def setUp(self):
        self.root = A.tk.Tk()
        self.root.withdraw()
        with mock.patch.object(
            A, "load_json", side_effect=lambda name: dict(CFG) if name == "config.json" else HEROES
        ):
            self.app = A.App(self.root)
        self.app.fetcher.collect = lambda: None

    def tearDown(self):
        try:
            self.app._on_close()
        except Exception:
            pass

    def _open_changelog(self):
        self.app._show_changelog()
        win = self.app._changelog_window
        win.withdraw()
        win._arm_outside_close()  # 测试无事件循环，手动完成延迟绑定
        return win

    def _open_update_window(self):
        """模拟手动更新：版本检查只标红点，用户点徽章才打开更新窗口。"""
        self.app._on_update_version(REMOTE, None)
        self.app._on_version_click()
        return self.app._update_window

    def test_top_right_has_both_versions_in_badge(self):
        self.assertIsNotNone(find_text_widget(self.root, "更新日志"))
        self.assertIsNotNone(find_text_widget(self.root, f"v{A.APP_VERSION}"))
        self.assertIsNotNone(find_text_widget(self.root, "当前版本"))
        self.assertIsNotNone(find_text_widget(self.root, "最新版本"))
        self.assertEqual(str(self.app.lbl_local_version.cget("text")), f"v{A.APP_VERSION}")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), "检查中…")
        self.assertEqual(self.app._version_state, "checking")
        self.assertEqual(str(self.app.lbl_version_dot.cget("text")).strip(), "",
                         "检查完成前不显示红点")

    def test_new_version_only_marks_badge_never_pops_dialog(self):
        self.app._on_update_version(REMOTE, None)
        self.assertIsNone(self.app._update_window, "绝不主动弹更新窗口")
        self.assertEqual(self.app._version_state, "update")
        # 两个版本号明面上都能看见
        self.assertEqual(str(self.app.lbl_local_version.cget("text")), f"v{A.APP_VERSION}")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), "v1.2.0")
        # 红点 + 醒目红框 + 点击引导
        self.assertEqual(str(self.app.lbl_version_dot.cget("text")), "●")
        self.assertEqual(str(self.app.lbl_version_dot.cget("fg")), A.DANGER)
        self.assertEqual(str(self.app.lbl_version_action.cget("text")), "点击更新")
        self.assertEqual(str(self.app.version_badge.cget("highlightbackground")), A.DANGER)

    def test_badge_width_stable_when_red_dot_appears(self):
        self.root.update_idletasks()
        width_before = self.app.version_badge.winfo_reqwidth()
        self.app._on_update_version(REMOTE, None)
        self.root.update_idletasks()
        self.assertEqual(self.app.version_badge.winfo_reqwidth(), width_before,
                         "亮红点不能让徽章忽宽忽窄、顶栏左右跳动")

    def test_badge_hover_keeps_dark_background_and_light_text(self):
        self.app._on_update_version(REMOTE, None)  # 红色警示态
        self.app._paint_badge(True)
        hover_bg = str(self.app.version_badge.cget("bg"))
        self.assertEqual(hover_bg, A.BADGE_ALERT_HOVER)
        for w in (self.app.lbl_local_version, self.app.lbl_remote_version,
                  self.app.lbl_version_action, self.app.lbl_version_dot):
            self.assertEqual(str(w.cget("bg")), hover_bg, "徽章整体同步换底")
            self.assertIn(str(w.cget("fg")), (A.TEXT, A.DANGER, A.MUTED),
                          "悬停时文字仍是浅色/警示色，不会白底白字")
        self.app._paint_badge(False)
        self.assertEqual(str(self.app.version_badge.cget("bg")), A.BADGE_ALERT_BG)

    def test_clicking_badge_without_new_version_never_opens_dialog(self):
        self.app._on_update_version({"version": A.APP_VERSION}, None)
        self.app._on_version_click()
        self.assertIsNone(self.app._update_window)
        self.assertIn("已是最新版本", self.app.lbl_status.cget("text"))

    def test_changelog_window_shows_current_content(self):
        self.app._show_changelog()
        win = self.app._changelog_window
        win.withdraw()
        text = win.text.get("1.0", "end")
        self.assertIn(f"v{A.APP_VERSION}", text)
        self.assertIn("版本检查", text)
        self.assertIn("v1.0.0", text)
        self.assertEqual(str(win.btn_close.cget("text")), "关闭")
        self.assertTrue(win._close_on_focus_out, "更新日志启用点击窗口外关闭")
        self.assertIs(win._toggle_widget, self.app.btn_changelog)
        self.app._show_changelog()
        self.assertIs(self.app._changelog_window, win, "重复点击不重复开窗")

    def test_changelog_window_uses_hanging_indent_and_conditional_scrollbar(self):
        self.app._show_changelog()
        win = self.app._changelog_window
        win.withdraw()
        self.assertGreater(int(win.text.tag_cget("item", "lmargin2")),
                           int(win.text.tag_cget("item", "lmargin1")),
                           "条目折行后应悬挂对齐，不能顶回行首")
        self.assertIn("•", win.text.get("1.0", "end"))
        win.destroy()
        self.app._changelog_window = None

        long_entries = [{"version": str(i), "date": "2026-11-11", "items": ["内容" * 40]}
                        for i in range(8)]
        win2 = A.ChangelogWindow(self.root, title="更新日志", subtitle="", entries=long_entries)
        win2.withdraw()
        self.assertEqual(win2.sb.winfo_manager(), "pack")
        self.assertEqual(int(win2.text.cget("height")), A.CHANGELOG_MAX_LINES)
        win2.destroy()

    def test_changelog_closes_when_focus_moves_outside(self):
        win = self._open_changelog()
        self.assertTrue(win._outside_armed)
        self.assertEqual(len(win._outside_binds), 2, "失焦 + 主窗口点击双保险")
        with mock.patch.object(win, "focus_get", return_value=self.root):
            win._on_focus_out()
            win.update_idletasks()  # 触发 after_idle
        self.assertEqual(win.winfo_exists(), 0, "点主窗口任意位置应关闭更新日志")

    def test_changelog_closes_on_click_of_non_focusable_widget(self):
        """点排行榜卡片等不抢焦点的主窗口组件也要关：旧逻辑靠焦点判断会漏关。"""
        win = self._open_changelog()
        # 主窗口内的一个普通组件（如「排行榜排名」卡片），点击不会抢焦点，
        # 真实场景下焦点仍停留在更新日志窗口上。
        card = ttk.Label(self.app.root, text="排行榜排名")
        with mock.patch.object(win, "focus_get", return_value=win):
            win._on_master_press(mock.Mock(widget=card))
            win.update_idletasks()
        self.assertEqual(win.winfo_exists(), 0, "点不抢焦点的主窗口组件也应立即关闭")

    def test_changelog_stays_open_when_focus_inside(self):
        win = self._open_changelog()
        for focus in (win.btn_close, win.text, win):
            with mock.patch.object(win, "focus_get", return_value=focus):
                win._close_if_focus_left()
            self.assertEqual(win.winfo_exists(), 1, "窗口内切换焦点不能关闭")

    def test_changelog_closes_when_app_loses_focus_or_other_window_active(self):
        for focus in (None, ""):
            win = self._open_changelog()
            with mock.patch.object(win, "focus_get", return_value=focus):
                win._close_if_focus_left()
            self.assertEqual(win.winfo_exists(), 0, "桌面/其它应用导致失焦也应关闭")
        other = A.tk.Toplevel(self.root)
        other.withdraw()
        win = self._open_changelog()
        with mock.patch.object(win, "focus_get", return_value=other):
            win._close_if_focus_left()
        self.assertEqual(win.winfo_exists(), 0, "切到别的窗口也应关闭")
        other.destroy()

    def test_changelog_button_click_does_not_reopen_or_close(self):
        win = self._open_changelog()
        with mock.patch.object(win, "focus_get", return_value=self.app.btn_changelog):
            win._on_master_press(mock.Mock(widget=self.app.btn_changelog))
            win.update_idletasks()
            win._on_focus_out()
            win.update_idletasks()
        self.assertEqual(win.winfo_exists(), 1, "点「更新日志」按钮本身不应误关窗口")
        with mock.patch.object(win, "focus_get", return_value=self.root):
            win._on_master_press(mock.Mock(widget=self.root))
            win.update_idletasks()
        self.assertEqual(win.winfo_exists(), 0, "点主窗口其它位置立即关闭")

    def test_outside_binds_removed_without_touching_master_bindings(self):
        before = self.root.bind("<ButtonPress-1>")
        self.root.bind("<ButtonPress-1>", lambda e: None, add="+")
        with_original = self.root.bind("<ButtonPress-1>")
        win = self._open_changelog()
        self.assertNotEqual(self.root.bind("<ButtonPress-1>"), with_original)
        win.destroy()
        self.assertEqual(self.root.bind("<ButtonPress-1>"), with_original,
                         "只摘除弹窗自己追加的绑定，主窗口原有绑定必须保留")
        self.assertEqual(win._outside_binds, [])
        self.assertFalse(win._outside_armed)
        self.root.bind("<ButtonPress-1>", before)

    def test_update_window_does_not_close_on_focus_out(self):
        with mock.patch.object(A, "apply_update"), mock.patch.object(A, "download_file"):
            win = self._open_update_window()
            win.withdraw()
            self.assertFalse(win._close_on_focus_out)
            self.assertEqual(win._outside_binds, [])
            with mock.patch.object(win, "focus_get", return_value=None):
                win._close_if_focus_left()
            self.assertEqual(win.winfo_exists(), 1, "发现新版本窗口不启用失焦关闭")
            win.destroy()

    def test_update_window_is_compact_with_visible_actions(self):
        with mock.patch.object(A, "apply_update"), mock.patch.object(A, "download_file"):
            win = self._open_update_window()
            win.withdraw()
            self.assertEqual(win.sb.winfo_manager(), "", "只有两条更新不该有滚动条")
            self.assertLessEqual(int(win.text.cget("height")), 8, "高度随内容收缩")
            self.assertLess(win.winfo_reqheight(), 420, "按钮区必须留在窗口内")
            self.assertIsNotNone(find_text_widget(win, f"v{A.APP_VERSION}   →   v1.2.0"),
                                 "大标题改为版本对比，不再重复窗口标题")
            self.assertIsNotNone(find_text_widget(
                win, "有新版本可用，可关闭本窗口继续使用当前版本，不会强制更新"))
            self.assertEqual(str(win.btn_update.cget("bg")), A.ACCENT, "主按钮用强调色")
            self.assertEqual(str(win.btn_later.cget("text")), "稍后再说")
            win.destroy()

    def test_click_badge_opens_optional_update_window(self):
        """用户主动点红点才弹窗，且仍然可关闭、不强制更新、不自动下载。"""
        with mock.patch.object(A, "apply_update") as apply_, \
             mock.patch.object(A, "download_file") as dl:
            self.assertIsNone(self.app._update_window)
            self.app._on_update_version(REMOTE, None)
            self.assertIsNone(self.app._update_window, "检查完成仍不弹窗")
            self.app._on_version_click()
            win = self.app._update_window
            self.assertIsInstance(win, A.UpdateWindow)
            win.withdraw()
            self.assertIn("发现新版本", win.title())
            text = win.text.get("1.0", "end")
            self.assertIn("新功能 A", text)
            self.assertNotIn("上一版内容", text, "只展示比本地新的条目")
            self.assertEqual(str(win.btn_update.cget("text")), "立即更新")
            self.assertEqual(str(win.btn_later.cget("text")), "稍后再说")
            self.assertFalse(self.app._closed, "弹窗不强制，不关闭主程序")
            win.destroy()
            self.assertFalse(self.app._closed, "关闭提示窗后照常使用当前版本")
            dl.assert_not_called()
            apply_.assert_not_called()

    def test_no_dialog_when_same_older_or_failed(self):
        self.app._on_update_version({"version": A.APP_VERSION}, None)
        self.assertIsNone(self.app._update_window)
        self.assertEqual(self.app._version_state, "latest")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), f"v{A.APP_VERSION}")
        self.assertEqual(str(self.app.lbl_version_dot.cget("text")).strip(), "", "同版本不亮红点")
        self.assertEqual(str(self.app.lbl_version_action.cget("text")), "已是最新")
        self.app._on_update_version({"version": "1.0.0"}, None)
        self.assertIsNone(self.app._update_window)
        self.app._on_update_version(None, "timeout")
        self.assertIsNone(self.app._update_window, "检查失败静默跳过")
        self.assertEqual(self.app._version_state, "failed")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), "未知")

    def test_manual_check_button_shows_only_on_failure(self):
        self.assertEqual(self.app.btn_version_check.winfo_manager(), "",
                         "默认隐藏，不占位")
        self.app._on_update_version(None, "timeout")
        self.assertEqual(self.app._version_state, "failed")
        self.assertEqual(self.app.btn_version_check.winfo_manager(), "pack",
                         "检查失败才显示「重试检查」按钮")
        self.app._on_update_version({"version": A.APP_VERSION}, None)
        self.assertEqual(self.app._version_state, "latest")
        self.assertEqual(self.app.btn_version_check.winfo_manager(), "",
                         "已是最新时隐藏")
        self.app._on_update_version(REMOTE, None)
        self.assertEqual(self.app._version_state, "update")
        self.assertEqual(self.app.btn_version_check.winfo_manager(), "",
                         "有新版时靠红点引导，不显示重试按钮")

    def test_manual_check_button_triggers_version_check(self):
        self.app._on_update_version(None, "timeout")  # 先进入失败态，按钮可见
        with mock.patch.object(A.threading, "Thread") as thread:
            self.app.btn_version_check.invoke()
        self.assertTrue(thread.called, "点「重试检查」应发起一次版本检查")
        self.assertEqual(self.app._version_state, "checking")
        self.assertEqual(self.app.btn_version_check.winfo_manager(), "",
                         "检查中隐藏按钮，避免重复触发")

    def test_queue_event_reaches_main_thread_badge_only(self):
        self.app._update_polling = True
        self.app._updates.put(("version", REMOTE, None))
        self.app._poll_updates()
        self.assertIsNone(self.app._update_window, "队列事件只更新徽章，不弹窗")
        self.assertEqual(self.app._version_state, "update")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), "v1.2.0")
        self.assertFalse(self.app._update_polling, "版本检查完成后停止轮询")

    def test_check_can_be_disabled_by_config(self):
        self.app.cfg["checkUpdate"] = 0
        with mock.patch.object(A.threading, "Thread") as thread:
            self.app.start_version_check()
        thread.assert_not_called()
        self.assertEqual(self.app._version_state, "off")
        self.assertEqual(str(self.app.lbl_remote_version.cget("text")), "未检查")

    def test_update_window_states(self):
        win = self._open_update_window()
        win.withdraw()
        win.set_busy()
        self.assertEqual(str(win.btn_update.cget("state")), "disabled")
        self.assertEqual(str(win.btn_update.cget("text")), "正在下载...")
        win.set_progress(50, 100)
        self.assertEqual(int(win.pbar.cget("value")), 50)
        self.assertIn("50%", win.lbl_state.cget("text"))
        win.set_ready()
        self.assertEqual(str(win.btn_update.cget("text")), "重启并完成更新")
        win.set_error("网络错误")
        self.assertEqual(str(win.btn_update.cget("text")), "重试")
        self.assertIn("网络错误", win.lbl_state.cget("text"))

    def test_source_mode_falls_back_to_download_page(self):
        with mock.patch.object(A.webbrowser, "open") as op, \
             mock.patch.object(A.sys, "frozen", False, create=True):
            self.app.start_update(REMOTE)
        op.assert_called_once_with(REMOTE["releasePage"])
        self.assertFalse(self.app._update_active, "源码模式不启动下载")

    def test_frozen_download_flow_through_queue(self):
        class FakeThread:
            def __init__(self, target=None, daemon=None):
                self.target = target

            def start(self):
                self.target()

        def fake_download(url, dest, progress=None):
            with open(dest, "wb") as f:
                f.write(b"MZ")
            return dest

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(A, "APP_DIR", d), \
             mock.patch.object(A.sys, "frozen", True, create=True), \
             mock.patch.object(A.threading, "Thread", FakeThread), \
             mock.patch.object(A, "download_file", side_effect=fake_download):
            self.app.start_update(REMOTE)
            dest = os.path.join(d, A.UPDATE_NEW_NAME)
            self.assertEqual(self.app._new_exe, dest)
            self.assertFalse(self.app._update_active, "下载完成后停止轮询")
            self.assertTrue(os.path.isfile(dest))

    def test_finish_update_only_after_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            new = os.path.join(d, A.UPDATE_NEW_NAME)
            with open(new, "wb") as f:
                f.write(b"MZ")
            self.app._new_exe = new
            with mock.patch.object(A, "apply_update") as apply_, \
                 mock.patch.object(self.app, "_on_close") as close:
                self.app.finish_update()
                apply_.assert_called_once_with(new)
                close.assert_called_once()
            self.app._new_exe = None
            with mock.patch.object(A, "apply_update") as apply_, \
                 mock.patch.object(self.app, "_on_close") as close:
                self.app.finish_update()
                apply_.assert_not_called()
                close.assert_not_called()

    def test_main_starts_version_check(self):
        import inspect
        src = inspect.getsource(A.main)
        self.assertIn("start_version_check()", src)


if __name__ == "__main__":
    unittest.main()
