"""代理配置回归：代理由 config.json 驱动，直接双击 exe 也能走代理（离线测试）。

覆盖：config 覆盖环境变量、分协议覆盖、环境变量兜底、显式直连、
      _ProxyOpener 保持 _opener 对象身份（兼容 R052 的 mock.patch）、
      App 启动即读 config 应用代理、源码运行能找到仓库根的 config.json。
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as A  # noqa: E402
import dota_stats.network as network  # noqa: E402

PROXY_VARS = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy")
ENV_PROXY = "http://127.0.0.1:49910"
CFG_PROXY = "http://127.0.0.1:18080"

CFG = {
    "userId": "129175832",
    "refreshToken": "RT",
    "tzOffset": 8,
    "gameDayStartHour": 8,
    "taskPoints": 300,
}
HEROES = {"nevermore": "影魔"}


def handler_proxies():
    """取出当前生效 opener 里 ProxyHandler 的代理字典。"""
    opener = network._opener
    inner = getattr(opener, "inner", opener)
    for handler in inner.handlers:
        if isinstance(handler, urllib.request.ProxyHandler):
            return handler.proxies
    return {}


class ProxyEnvMixin:
    """隔离并还原代理环境变量，避免测试之间互相污染。"""

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in PROXY_VARS}
        for key in PROXY_VARS:
            os.environ.pop(key, None)
        os.environ["HTTP_PROXY"] = ENV_PROXY
        os.environ["HTTPS_PROXY"] = ENV_PROXY
        network.configure_proxy({})  # 基线：沿用环境变量
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        network.configure_proxy({})


class TestProxyConfig(ProxyEnvMixin, unittest.TestCase):
    def test_config_proxy_overrides_env_and_enters_opener(self):
        settings = A.configure_proxy({"proxy": CFG_PROXY})
        self.assertEqual(settings, {"http": CFG_PROXY, "https": CFG_PROXY})
        self.assertEqual(A._proxy_host(), CFG_PROXY)
        self.assertEqual(handler_proxies(), {"http": CFG_PROXY, "https": CFG_PROXY})
        self.assertEqual(os.environ["HTTP_PROXY"], CFG_PROXY)
        self.assertEqual(os.environ["HTTPS_PROXY"], CFG_PROXY)

    def test_per_scheme_override(self):
        A.configure_proxy({"proxy": CFG_PROXY, "httpsProxy": "http://127.0.0.1:18081"})
        self.assertEqual(handler_proxies()["http"], CFG_PROXY)
        self.assertEqual(handler_proxies()["https"], "http://127.0.0.1:18081")

    def test_missing_proxy_key_falls_back_to_env(self):
        settings = A.configure_proxy(dict(CFG))
        self.assertEqual(settings, {"http": ENV_PROXY, "https": ENV_PROXY})
        self.assertEqual(handler_proxies(), {"http": ENV_PROXY, "https": ENV_PROXY})

    def test_no_proxy_at_all_means_direct(self):
        for key in PROXY_VARS:
            os.environ.pop(key, None)
        settings = A.configure_proxy({})
        self.assertEqual(settings, {"http": "", "https": ""})
        self.assertEqual(handler_proxies(), {})
        self.assertIsNone(A._proxy_host())

    def test_explicit_off_disables_proxy_even_with_env_set(self):
        settings = A.configure_proxy({"proxy": ""})
        self.assertEqual(settings, {"http": "", "https": ""})
        self.assertEqual(handler_proxies(), {})
        self.assertIsNone(A._proxy_host())
        for key in PROXY_VARS:
            self.assertIsNone(os.environ.get(key), key)

    def test_proxy_without_scheme_is_normalized(self):
        A.configure_proxy({"proxy": "127.0.0.1:18080"})
        self.assertEqual(handler_proxies()["https"], CFG_PROXY)

    def test_opener_identity_is_stable_for_patch_compat(self):
        before = A._opener
        A.configure_proxy({"proxy": CFG_PROXY})
        self.assertIs(A._opener, before, "_opener 被替换会让门面 / updater 的静态引用失效")
        self.assertIs(network._opener, before)

    def test_http_json_still_uses_the_opener_object(self):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"ok": 1}'

        class FakeOpener:
            def open(self, req, timeout=None):
                return FakeResp()

        with mock.patch.object(A, "_opener", FakeOpener()):
            self.assertEqual(A.http_json("https://example.invalid/x"), {"ok": 1})


class TestAppAppliesProxy(ProxyEnvMixin, unittest.TestCase):
    def test_app_reads_proxy_from_config_json_at_startup(self):
        root = A.tk.Tk()
        root.withdraw()
        tmpdir = tempfile.mkdtemp(prefix="dota-proxy-test-")
        self.addCleanup(shutil.rmtree, tmpdir, True)
        cfg = dict(CFG, proxy=CFG_PROXY, dbPath=os.path.join(tmpdir, "proxy.db"))
        with mock.patch.object(
            A, "load_json",
            side_effect=lambda name: dict(cfg) if name == "config.json" else HEROES,
        ):
            app = A.App(root)
        try:
            self.assertEqual(network._proxy_settings["https"], CFG_PROXY)
            self.assertEqual(handler_proxies(), {"http": CFG_PROXY, "https": CFG_PROXY})
        finally:
            app._on_close()


class TestLoadJsonPaths(unittest.TestCase):
    def test_source_run_finds_config_in_parent_of_package_dir(self):
        """源码模式 APP_DIR 是 dota_stats/，配置在仓库根，也要能读到。"""
        with tempfile.TemporaryDirectory() as d:
            package_dir = os.path.join(d, "dota_stats")
            os.makedirs(package_dir)
            with open(os.path.join(d, "sample.json"), "w", encoding="utf-8") as f:
                json.dump({"proxy": CFG_PROXY}, f)
            with mock.patch.object(A, "APP_DIR", package_dir):
                self.assertEqual(A.load_json("sample.json")["proxy"], CFG_PROXY)

    def test_missing_file_reports_paths(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(A, "APP_DIR", d):
                with self.assertRaises(FileNotFoundError) as ctx:
                    A.load_json("definitely-missing.json")
        self.assertIn("definitely-missing.json", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
