"""架构回归：app.py 拆成兼容门面后，对外名称、patch 语义与模块边界不能退化。

这些测试不创建 Tk 窗口、不写本地库（遵守 R050 测试隔离口径）。
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as A  # noqa: E402
import dota_stats.config as config  # noqa: E402
import dota_stats.network as network  # noqa: E402
import dota_stats.updater as updater  # noqa: E402
from dota_stats import ui_build, ui_fetch, ui_render, ui_sync, ui_version  # noqa: E402

# 拆分前 app.py 的模块级名字（含测试用 mock.patch.object(app, ...) 的模块对象）
LEGACY_NAMES = (
    "APP_DIR", "APP_VERSION", "CHANGELOG", "API_TIMEOUT", "TOKEN_TIMEOUT",
    "FETCH_MAX_ATTEMPTS", "FETCH_RETRY_INTERVAL_S", "AUTO_REFRESH_INTERVAL_MS",
    "PREF_AUTO_REFRESH", "BG", "ACCENT", "FONT_UI", "S1", "SORT_KEYS",
    "MEMBER_STEP", "WARRIOR_STEP",
    "load_json", "http_json", "refresh_id_token", "api_get", "get_game_date",
    "local_time_str", "fmt_duration", "level_need", "level_cum", "level_from_exp",
    "fetch_with_retry", "version_tuple", "is_newer", "fetch_version_info",
    "new_changelog_entries", "download_file", "build_update_bat", "apply_update",
    "_divider", "_changelog_metrics", "_render_changelog",
    "DataFetcher", "FetchCancelled", "RefreshController",
    "ChangelogWindow", "UpdateWindow", "SyncWindow", "App", "main",
    "storage", "subprocess", "threading", "time", "sys", "webbrowser", "tk", "ttk",
)

MODULES = (
    "config", "domain", "network", "updater", "theme", "windows",
    "ui_build", "ui_fetch", "ui_render", "ui_version", "ui_sync", "app_core",
)


class TestFacadeCompatibility(unittest.TestCase):
    def test_legacy_names_still_exported(self):
        missing = [n for n in LEGACY_NAMES if not hasattr(A, n)]
        self.assertFalse(missing, "兼容门面缺少旧名称: %s" % missing)

    def test_patch_on_app_reaches_implementation_modules(self):
        """mock.patch.object(app, 'http_json') 必须同步到所有引用它的实现模块。"""
        sentinel = object()
        original = network.http_json
        with mock.patch.object(A, "http_json", sentinel):
            self.assertIs(A.http_json, sentinel)
            self.assertIs(network.http_json, sentinel)
            self.assertIs(updater.http_json, sentinel)
        self.assertIs(network.http_json, original)
        self.assertIs(updater.http_json, original)

    def test_patch_constant_reaches_definition_module(self):
        with mock.patch.object(A, "APP_DIR", "X-DIR"):
            self.assertEqual(config.APP_DIR, "X-DIR")
            self.assertEqual(updater.APP_DIR, "X-DIR")
        self.assertNotEqual(config.APP_DIR, "X-DIR")

    def test_app_is_composed_from_mixins(self):
        for mixin_mod in (ui_build, ui_fetch, ui_render, ui_sync, ui_version):
            mixin = next(v for k, v in vars(mixin_mod).items()
                         if k.endswith("Mixin") and isinstance(v, type))
            self.assertTrue(issubclass(A.App, mixin), mixin.__name__)

    def test_facade_stays_thin(self):
        """门面只放导出与入口，不允许再把业务逻辑堆回 app.py。"""
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as f:
            nlines = len(f.readlines())
        self.assertLess(nlines, 300, "app.py 已膨胀到 %d 行，请检查是否误把实现写回门面" % nlines)

    def test_all_submodules_import_independently(self):
        import importlib
        for name in MODULES:
            importlib.import_module("dota_stats.%s" % name)


if __name__ == "__main__":
    unittest.main()
