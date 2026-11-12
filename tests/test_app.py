"""app.py 离线单元测试：等级公式、超时口径、token 缓存、自动刷新调度、GUI 冒烟。"""

import json
import os
import sys
import time
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

INFO = {
    "seasonLevel": 71,
    "seasonCurrrentLevelPoint": 3211,
    "seasonNextLevelPoint": 10311,
    "seasonPointTotal": 251711,
    "memberLevel": 20,
    "memberCurrentLevelPoint": 550,
    "memberNextLevelPoint": 2500,
    "memberPointTotal": 28100,
    "matchCount": 100,
    "winCount": 55,
}

RECENT = [
    {
        "endedAt": "2026-11-10T12:00:00Z",
        "durationSec": 1800,
        "battlePoints": 105,
        "heroName": "npc_dota_hero_nevermore",
        "difficulty": 3,
        "level": 71,
        "win": True,
        "kills": 5,
        "deaths": 2,
        "assists": 8,
        "lastHits": 100,
        "totalGoldEarned": 12000,
        "heroDamage": 30000,
        "damageTaken": 15000,
        "towerKills": 2,
    },
    {
        "endedAt": "2026-11-10T13:00:00Z",
        "durationSec": 1200,
        "battlePoints": 95,
        "heroName": "npc_dota_hero_nevermore",
    },
]

HEROES = {"nevermore": "影魔"}


def fake_api(token, url, timeout=A.API_TIMEOUT, calls=None, fail_recent=False):
    if calls is not None:
        calls.append((url, timeout, token))
    if url.endswith("/ranking"):
        return {"rank": 12}
    if url.endswith("/info?include=member"):
        return INFO
    if "stats/recent" in url:
        if fail_recent:
            raise TimeoutError("timed out")
        return RECENT
    raise AssertionError("未预期的接口: " + url)


class TestLevelRules(unittest.TestCase):
    """§5 业务口径：与网站接口阈值对齐，不得漂移。"""

    def test_member(self):
        self.assertEqual(A.level_need(20, A.MEMBER_STEP, A.MEMBER_BASE), 1950)
        self.assertEqual(A.level_cum(20, A.MEMBER_STEP, A.MEMBER_BASE), 27550)
        self.assertEqual(A.level_from_exp(28100, A.MEMBER_STEP, A.MEMBER_BASE), 20)

    def test_warrior(self):
        self.assertEqual(A.level_need(71, A.WARRIOR_STEP, A.WARRIOR_BASE), 7100)
        self.assertEqual(A.level_cum(71, A.WARRIOR_STEP, A.WARRIOR_BASE), 248500)
        self.assertEqual(A.level_from_exp(251711, A.WARRIOR_STEP, A.WARRIOR_BASE), 71)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self):
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append((req, timeout))
        return FakeResponse({"id_token": "ID", "rank": 1})


class TestHttpTimeout(unittest.TestCase):
    def test_layered_timeouts(self):
        op = FakeOpener()
        with mock.patch.object(A, "_opener", op):
            A.http_json("https://x/business")
            A.refresh_id_token("RT")
            A.api_get("T", "https://x/other", timeout=2.5)
            A.http_json("https://x/explicit", timeout=1)
        self.assertEqual(
            [c[1] for c in op.calls],
            [A.API_TIMEOUT, A.TOKEN_TIMEOUT, 2.5, 1],
        )
        self.assertEqual(A.API_TIMEOUT, 5.0)
        self.assertEqual(A.TOKEN_TIMEOUT, 10.0)
        self.assertEqual(A.AUTO_REFRESH_INTERVAL_MS, 5000)


class TestDataFetcher(unittest.TestCase):
    def setUp(self):
        self.fetcher = A.DataFetcher(dict(CFG), HEROES)

    def test_collect_success(self):
        calls = []

        def api(token, url, timeout=A.API_TIMEOUT):
            return fake_api(token, url, timeout, calls)

        with mock.patch.object(A, "refresh_id_token", return_value="ID") as rt, mock.patch.object(
            A, "api_get", side_effect=api
        ):
            data = self.fetcher.collect()

        self.assertEqual(data["warnings"], [])
        self.assertEqual(data["profile"]["rank"], 12)
        self.assertEqual(data["profile"]["seasonLevel"], 71)
        self.assertEqual(data["profile"]["seasonPointTotal"], 251711)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["rows"][0]["hero"], "影魔")
        self.assertAlmostEqual(data["avgDurationSec"], 1500)
        self.assertEqual(data["days"][0]["count"], 2)
        self.assertEqual(data["days"][0]["points"], 200)
        self.assertTrue(all(t == 5.0 for _, t, _ in calls))
        self.assertTrue(all(tok == "ID" for _, _, tok in calls))
        rt.assert_called_once_with("RT", timeout=10.0)

    def test_token_cache(self):
        def api(token, url, timeout=A.API_TIMEOUT):
            return fake_api(token, url, timeout)

        with mock.patch.object(A, "refresh_id_token", return_value="ID") as rt, mock.patch.object(
            A, "api_get", side_effect=api
        ):
            self.fetcher.collect()
            self.fetcher.collect()
        self.assertEqual(rt.call_count, 1, "5 秒一轮不应重复换取 id_token")

    def test_partial_failure_is_visible(self):
        def api(token, url, timeout=A.API_TIMEOUT):
            return fake_api(token, url, timeout, fail_recent=True)

        with mock.patch.object(A, "refresh_id_token", return_value="ID"), mock.patch.object(
            A, "api_get", side_effect=api
        ):
            data = self.fetcher.collect()
        self.assertEqual(len(data["warnings"]), 1)
        self.assertIn("近期战绩", data["warnings"][0])
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["profile"]["rank"], 12)

    def test_token_failure_raises_and_clears_cache(self):
        def api(token, url, timeout=A.API_TIMEOUT):
            return fake_api(token, url, timeout)

        with mock.patch.object(A, "refresh_id_token", side_effect=TimeoutError("timeout")):
            with self.assertRaisesRegex(RuntimeError, "登录凭证刷新失败"):
                self.fetcher.collect()

        with mock.patch.object(A, "refresh_id_token", return_value="ID") as rt, mock.patch.object(
            A, "api_get", side_effect=api
        ):
            self.fetcher.collect()
        self.assertEqual(rt.call_count, 1)

    def test_config_overrides(self):
        fetcher = A.DataFetcher(dict(CFG, apiTimeout=2, tokenTimeout=3), HEROES)
        self.assertEqual((fetcher.api_timeout, fetcher.token_timeout), (2.0, 3.0))
        calls = []

        def api(token, url, timeout=A.API_TIMEOUT):
            return fake_api(token, url, timeout, calls)

        with mock.patch.object(A, "refresh_id_token", return_value="ID") as rt, mock.patch.object(
            A, "api_get", side_effect=api
        ):
            fetcher.collect()
        self.assertTrue(all(t == 2.0 for _, t, _ in calls))
        rt.assert_called_once_with("RT", timeout=3.0)


class FakeClock:
    """记录 after(delay, fn) 的假时钟，用来验证「完成后等 5 秒」。"""

    def __init__(self):
        self.timers = {}
        self.cancelled = []
        self.seq = 0

    def after(self, delay, fn):
        self.seq += 1
        self.timers[self.seq] = (delay, fn)
        return self.seq

    def after_cancel(self, tid):
        self.cancelled.append(tid)
        self.timers.pop(tid, None)

    def fire(self):
        assert len(self.timers) == 1, f"应有且仅有一个定时器，实际 {len(self.timers)}"
        tid, (delay, fn) = next(iter(self.timers.items()))
        self.timers.pop(tid)
        fn()
        return delay

    def delay(self):
        assert len(self.timers) == 1, f"应有且仅有一个定时器，实际 {len(self.timers)}"
        return next(iter(self.timers.values()))[0]


class TestRefreshController(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.starts = []
        self.ctrl = A.RefreshController(
            self.clock.after, self.clock.after_cancel, lambda: self.starts.append(1)
        )

    def test_wait_after_finish_not_after_start(self):
        self.assertTrue(self.ctrl.schedule(0))
        self.assertEqual(self.clock.delay(), 0)
        self.clock.fire()
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(len(self.clock.timers), 0, "刷新进行中不该安排下一轮")
        self.assertTrue(self.ctrl.finished())
        self.assertEqual(self.clock.delay(), 5000)
        self.clock.fire()
        self.assertEqual(len(self.starts), 2)
        self.assertEqual(self.ctrl.rounds, 2)

    def test_no_concurrent_requests(self):
        self.assertTrue(self.ctrl.request())
        self.assertFalse(self.ctrl.request())
        self.assertEqual(len(self.starts), 1)
        self.assertTrue(self.ctrl.finished())
        self.assertTrue(self.ctrl.request())
        self.assertEqual(len(self.starts), 2)
        self.assertEqual(len(self.clock.timers), 0, "手动刷新应取消排队的定时器")

    def test_manual_request_resets_pending_timer(self):
        self.ctrl.schedule(5000)
        self.ctrl.request()
        self.assertEqual(self.clock.cancelled, [1])
        self.assertEqual(len(self.clock.timers), 0)

    def test_disable_enable(self):
        self.ctrl.schedule(5000)
        self.ctrl.set_enabled(False)
        self.assertEqual(len(self.clock.timers), 0)
        self.assertFalse(self.ctrl.finished())
        self.assertEqual(len(self.clock.timers), 0)
        self.assertTrue(self.ctrl.set_enabled(True))
        self.assertEqual(self.clock.delay(), 0, "重新开启应立刻刷新一轮")

    def test_stop(self):
        self.ctrl.request()
        self.ctrl.stop()
        self.assertFalse(self.ctrl.finished())
        self.assertFalse(self.ctrl.request())
        self.assertFalse(self.ctrl.tick())
        self.assertEqual(len(self.clock.timers), 0)
        self.assertEqual(len(self.starts), 1)

    def test_custom_interval(self):
        ctrl = A.RefreshController(
            self.clock.after, self.clock.after_cancel, lambda: None, interval_ms=50
        )
        ctrl.request()
        ctrl.finished()
        self.assertEqual(self.clock.delay(), 50)

    def test_start_failure_does_not_stuck(self):
        def boom():
            raise OSError("boom")

        ctrl = A.RefreshController(self.clock.after, self.clock.after_cancel, boom)
        with self.assertRaises(OSError):
            ctrl.request()
        self.assertFalse(ctrl.running)
        self.assertTrue(ctrl.finished())


class TestGuiSmoke(unittest.TestCase):
    """真实 tkinter（隐藏窗口）+ mock 取数：验证自动刷新确实连续多轮。"""

    def test_auto_refresh_loops(self):
        tk = A.tk
        # checkUpdate=0 关闭版本检查，避免本轮测试真联网；刷新循环只验证三个数据接口
        cfg = dict(CFG, autoRefreshIntervalMs=30, checkUpdate=0)
        root = tk.Tk()
        root.withdraw()
        app = None
        try:

            def fake_load(name):
                return cfg if name == "config.json" else HEROES

            with mock.patch.object(A, "load_json", side_effect=fake_load):
                app = A.App(root)

            count = [0]

            def fake_fetch():
                # 三个接口各自独立线程调用，每次取数 +1；返回与 PROFILE 一致的数据
                count[0] += 1
                return dict(PROFILE)

            app.fetcher.fetch_ranking = lambda: fake_fetch()
            app.fetcher.fetch_info = lambda: fake_fetch()
            app.fetcher.fetch_recent = lambda: (fake_fetch(), {"matches": []})[1]

            deadline = time.monotonic() + 5

            # 用真实事件循环驱动：应用内部有自续 after 轮询，update() 会一直不返回，
            # 因此这里跑 mainloop，条件满足或超时后 quit 退出。
            def check():
                # 每轮 3 次接口调用；跑满至少 3 轮 = 9 次调用且当前不在刷新中
                if (count[0] >= 9 and not app.ctrl.running) or time.monotonic() > deadline:
                    root.quit()
                    return
                root.after(20, check)

            root.after(20, check)
            root.mainloop()

            self.assertGreaterEqual(count[0], 9, "自动刷新应连续跑完至少 3 轮（每轮 3 接口）")
            self.assertIn("更新于", app.lbl_updated.cget("text"))
            self.assertEqual(app.lbl_status.cget("text"), "")
            self.assertFalse(app.ctrl.running)
        finally:
            if app is not None:
                app._on_close()
            else:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
