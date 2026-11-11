"""版本检查、可选自动更新与更新日志的离线单元测试（隐藏窗口，不联网、不覆盖 exe）。"""

import json
import os
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

    def test_top_right_has_changelog_button_and_version(self):
        self.assertIsNotNone(find_text_widget(self.root, "更新日志"))
        self.assertIsNotNone(find_text_widget(self.root, f"v{A.APP_VERSION}"))

    def test_changelog_window_shows_current_content(self):
        self.app._show_changelog()
        win = self.app._changelog_window
        win.withdraw()
        text = win.text.get("1.0", "end")
        self.assertIn(f"v{A.APP_VERSION}", text)
        self.assertIn("版本检查", text)
        self.assertIn("v1.0.0", text)
        self.assertEqual(str(win.btn_close.cget("text")), "关闭")
        self.app._show_changelog()
        self.assertIs(self.app._changelog_window, win, "重复点击不重复开窗")

    def test_new_version_opens_optional_dialog(self):
        with mock.patch.object(A, "apply_update") as apply_, \
             mock.patch.object(A, "download_file") as dl:
            self.app._on_update_version(REMOTE, None)
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
        self.app._on_update_version({"version": "1.0.0"}, None)
        self.assertIsNone(self.app._update_window)
        self.app._on_update_version(None, "timeout")
        self.assertIsNone(self.app._update_window, "检查失败静默跳过")

    def test_queue_event_reaches_main_thread_dialog(self):
        self.app._update_polling = True
        self.app._updates.put(("version", REMOTE, None))
        self.app._poll_updates()
        self.assertIsInstance(self.app._update_window, A.UpdateWindow)
        self.app._update_window.withdraw()
        self.assertFalse(self.app._update_polling, "弹窗后停止轮询")

    def test_check_can_be_disabled_by_config(self):
        self.app.cfg["checkUpdate"] = 0
        with mock.patch.object(A.threading, "Thread") as thread:
            self.app.start_version_check()
        thread.assert_not_called()

    def test_update_window_states(self):
        self.app._on_update_version(REMOTE, None)
        win = self.app._update_window
        win.withdraw()
        win.set_busy()
        self.assertIn("disabled", win.btn_update.state())
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
