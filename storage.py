"""本地 SQLite 战绩库：接口只负责写库，界面只读库。

设计要点（见 AGENTS.md §6 规则）：
- 唯一键 (user_id, ended_at)：接口记录没有稳定的 matchId（多为 "0"），
  换成 ended_at 做复合唯一索引，重复插入由数据库兜住，绝不产生重复行。
- 派生列 game_date / game_month 在写入时按「游戏日」口径算好并建索引，
  每日/每月统计直接走 SQL 聚合，避免每轮把全部对局读回 Python。
- 每个线程各自建连接（sqlite3 连接不跨线程共享），配合 busy_timeout 串行写入。
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB_FILE_NAME = "matches.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT    NOT NULL,
    ended_at       TEXT    NOT NULL,
    game_date      TEXT    NOT NULL,
    game_month     TEXT    NOT NULL,
    duration_sec   INTEGER NOT NULL DEFAULT 0,
    battle_points  INTEGER NOT NULL DEFAULT 0,
    win            INTEGER NOT NULL DEFAULT 0,
    raw_json       TEXT    NOT NULL,
    UNIQUE (user_id, ended_at)
);
CREATE INDEX IF NOT EXISTS idx_matches_user_ended ON matches(user_id, ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_matches_user_date  ON matches(user_id, game_date);
CREATE INDEX IF NOT EXISTS idx_matches_user_month ON matches(user_id, game_month);
CREATE TABLE IF NOT EXISTS sync_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def resolve_db_path(cfg, app_dir):
    """config.json 的 dbPath 可覆盖默认位置；相对路径相对程序目录。"""
    p = (cfg or {}).get("dbPath") or os.path.join(app_dir, DB_FILE_NAME)
    if not os.path.isabs(p):
        p = os.path.join(app_dir, p)
    return p


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db(db_path):
    """建表 + 索引（幂等，可反复调用）。返回规范化后的路径。"""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


def game_date_of(utc_str, tz_offset=8, start_hour=8):
    """与 app.get_game_date 同口径：按 start_hour 点为界划分游戏日。"""
    dt = datetime.fromisoformat(str(utc_str).replace("Z", "+00:00")).astimezone(
        timezone(timedelta(hours=tz_offset))
    )
    if dt.hour < start_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def upsert_matches(db_path, user_id, matches, tz_offset=8, start_hour=8):
    """幂等写入一批原始对局；返回新增条数（重复记录被唯一索引忽略）。

    INSERT OR IGNORE 保证「相同数据不重复插入」，也保证全量同步与每轮
    recent 写库并发时不会互相干扰。raw_json 保留完整字段供战绩表复用
    DataFetcher.derive_rows_days（英雄映射/时间格式/效率口径不分叉）。
    """
    if not matches:
        return 0
    inserted = 0
    with connect(db_path) as conn:
        for m in matches:
            ended = m.get("endedAt")
            if not ended:
                continue
            date = game_date_of(ended, tz_offset, start_hour)
            cur = conn.execute(
                "INSERT OR IGNORE INTO matches "
                "(user_id, ended_at, game_date, game_month, duration_sec, "
                " battle_points, win, raw_json) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(user_id), str(ended), date, date[:7],
                    int(m.get("durationSec") or 0),
                    int(m.get("battlePoints") or 0),
                    1 if m.get("win") else 0,
                    json.dumps(m, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            inserted += max(0, cur.rowcount)
    return inserted


def count_matches(db_path, user_id):
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM matches WHERE user_id=?", (str(user_id),)
        ).fetchone()[0]


def stats_signature(db_path, user_id):
    """库内数据是否变化的轻量签名：场数 + 最新一场时间。"""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*), MAX(ended_at) FROM matches WHERE user_id=?",
            (str(user_id),),
        ).fetchone()
    return (row[0], row[1])


def _range_start(db_path, user_id, days):
    """最近 N 个游戏日的起始日期；days=None 表示全部。"""
    if not days or days <= 0:
        return None
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT game_date FROM matches WHERE user_id=? "
            "ORDER BY game_date DESC LIMIT ?",
            (str(user_id), int(days)),
        ).fetchall()
    return rows[-1][0] if rows else None


def fetch_matches(db_path, user_id, days=None):
    """按 ended_at 倒序取回原始对局 dict 列表（供 derive_rows_days 复用）。"""
    start = _range_start(db_path, user_id, days)
    sql = "SELECT raw_json FROM matches WHERE user_id=?"
    args = [str(user_id)]
    if start:
        sql += " AND game_date>=?"
        args.append(start)
    sql += " ORDER BY ended_at DESC"
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [json.loads(r[0]) for r in rows]


def _fmt_time(sec):
    total_min = round((sec or 0) / 60)
    h, m = divmod(total_min, 60)
    return f"{h}时{m}分" if h else f"{m}分"


def daily_stats(db_path, user_id, task_points=300, days=None):
    """每日统计：与 derive_rows_days 的 days 结构完全一致。

    eff = (当日积分 - 每日任务分) / 当日游戏小时数，沿用现有口径。
    """
    start = _range_start(db_path, user_id, days)
    sql = (
        "SELECT game_date, COUNT(*), SUM(battle_points), SUM(duration_sec) "
        "FROM matches WHERE user_id=?"
    )
    args = [str(user_id)]
    if start:
        sql += " AND game_date>=?"
        args.append(start)
    sql += " GROUP BY game_date ORDER BY game_date DESC"
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for date, count, points, sec in rows:
        points, sec = int(points or 0), sec or 0
        hours = sec / 3600
        out.append({
            "date": date,
            "count": count,
            "points": points,
            "time": _fmt_time(sec),
            "eff": (points - task_points) / hours if hours else 0,
        })
    return out


def monthly_stats(db_path, user_id, task_points=300):
    """每月统计：按自然月聚合；任务分按当月有对局的游戏日数累加。"""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT game_month, COUNT(*), SUM(battle_points), SUM(duration_sec), "
            "COUNT(DISTINCT game_date) FROM matches WHERE user_id=? "
            "GROUP BY game_month ORDER BY game_month DESC",
            (str(user_id),),
        ).fetchall()
    out = []
    for month, count, points, sec, day_count in rows:
        points, sec = int(points or 0), sec or 0
        hours = sec / 3600
        out.append({
            "date": month,
            "count": count,
            "points": points,
            "time": _fmt_time(sec),
            "eff": (points - task_points * (day_count or 1)) / hours if hours else 0,
        })
    return out


def set_meta(db_path, key, value):
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sync_meta(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(key), str(value)),
        )


def get_meta(db_path, key, default=""):
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM sync_meta WHERE key=?", (str(key),)
        ).fetchone()
    return row[0] if row else default


def indexes(db_path):
    """返回 (名称, 是否唯一, 列) 列表，供自测核对索引与唯一索引。"""
    with connect(db_path) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='matches'"
        ).fetchall()]
        out = []
        for name in names:
            info = conn.execute(
                "PRAGMA index_info('%s')" % name.replace("'", "''")
            ).fetchall()
            uniq = conn.execute("PRAGMA index_list(matches)").fetchall()
            is_unique = any(r[1] == name and r[2] for r in uniq)
            out.append((name, bool(is_unique), tuple(r[2] for r in info)))
        return out
