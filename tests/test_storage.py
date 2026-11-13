"""本地 SQLite 战绩库：唯一索引、幂等写入、日/月聚合与范围查询。"""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import storage  # noqa: E402


def match(utc, bp=100, sec=1200):
    return {
        "matchId": "0", "endedAt": utc, "durationSec": sec, "battlePoints": bp,
        "win": True, "heroName": "npc_dota_hero_phantom_assassin", "kills": 10,
    }


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dota-storage-test-")
        self.db = os.path.join(self.tmpdir, "matches.db")
        storage.init_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_indexes_and_unique_key(self):
        idx = storage.indexes(self.db)
        self.assertTrue(
            any(unique and cols == ("user_id", "ended_at") for _, unique, cols in idx),
            "必须有 (user_id, ended_at) 复合唯一索引",
        )
        for cols in (("user_id", "ended_at"), ("user_id", "game_date"),
                     ("user_id", "game_month")):
            self.assertTrue(any(c == cols for _, _, c in idx), f"缺少索引 {cols}")

    def test_duplicate_insert_is_ignored(self):
        ms = [match("2026-11-04T14:00:00.000Z"), match("2026-10-20T10:00:00.000Z")]
        self.assertEqual(storage.upsert_matches(self.db, "u1", ms), 2)
        self.assertEqual(storage.upsert_matches(self.db, "u1", ms), 0,
                         "相同数据重复插入必须被唯一索引忽略")
        mixed = ms[:1] + [match("2026-11-05T10:00:00.000Z")]
        self.assertEqual(storage.upsert_matches(self.db, "u1", mixed), 1,
                         "一批里只应插入没见过的那一条")
        self.assertEqual(storage.count_matches(self.db, "u1"), 3)

    def test_multi_user_isolation(self):
        ms = [match("2026-11-04T14:00:00.000Z")]
        storage.upsert_matches(self.db, "u1", ms)
        storage.upsert_matches(self.db, "u2", ms)
        self.assertEqual(storage.count_matches(self.db, "u1"), 1)
        self.assertEqual(storage.count_matches(self.db, "u2"), 1)
        self.assertEqual(len(storage.daily_stats(self.db, "u1")), 1)

    def test_game_day_boundary(self):
        # UTC 01:00 = 北京 09:00，仍算当天；UTC 前一天 23:00 = 北京 07:00，归前一天
        self.assertEqual(storage.game_date_of("2026-11-04T01:00:00.000Z"), "2026-11-04")
        self.assertEqual(storage.game_date_of("2026-11-03T23:00:00.000Z"), "2026-11-03")

    def test_daily_and_monthly_stats(self):
        storage.upsert_matches(self.db, "u1", [
            match("2026-11-04T14:00:00.000Z", bp=108, sec=698),
            match("2026-11-04T10:00:00.000Z", bp=120, sec=1200),
            match("2026-10-20T10:00:00.000Z", bp=95, sec=900),
        ])
        days = storage.daily_stats(self.db, "u1", task_points=300)
        self.assertEqual([d["date"] for d in days], ["2026-11-04", "2026-10-20"])
        self.assertEqual(days[0]["count"], 2)
        self.assertEqual(days[0]["points"], 228)
        self.assertEqual(days[0]["time"], "32分")
        months = storage.monthly_stats(self.db, "u1", task_points=300)
        self.assertEqual([m["date"] for m in months], ["2026-11", "2026-10"])
        self.assertEqual(months[0]["count"], 2)
        # 最近 1 个游戏日：只保留 11-04 的两场
        self.assertEqual([d["date"] for d in storage.daily_stats(self.db, "u1", days=1)],
                         ["2026-11-04"])
        self.assertEqual(len(storage.fetch_matches(self.db, "u1", days=1)), 2)

    def test_fetch_matches_returns_full_raw_record_in_desc_order(self):
        storage.upsert_matches(self.db, "u1", [
            match("2026-11-01T10:00:00.000Z"),
            match("2026-11-04T10:00:00.000Z"),
        ])
        rows = storage.fetch_matches(self.db, "u1")
        self.assertEqual([r["endedAt"] for r in rows],
                         ["2026-11-04T10:00:00.000Z", "2026-11-01T10:00:00.000Z"])
        self.assertEqual(rows[0]["kills"], 10, "必须保留完整原始字段供战绩表复用")

    def test_signature_meta_and_missing_fields(self):
        self.assertEqual(storage.stats_signature(self.db, "u1"), (0, None))
        storage.upsert_matches(self.db, "u1", [
            {"endedAt": "2026-11-04T10:00:00.000Z"},  # 缺字段也不应炸
            {"heroName": "x"},                        # 无 endedAt 必须跳过
        ])
        self.assertEqual(storage.count_matches(self.db, "u1"), 1)
        self.assertEqual(storage.stats_signature(self.db, "u1"),
                         (1, "2026-11-04T10:00:00.000Z"))
        storage.set_meta(self.db, "last_full_sync", "2026-11-13 12:00:00")
        storage.set_meta(self.db, "last_full_sync", "2026-11-13 13:00:00")
        self.assertEqual(storage.get_meta(self.db, "last_full_sync"),
                         "2026-11-13 13:00:00")


if __name__ == "__main__":
    unittest.main()
