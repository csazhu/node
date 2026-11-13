"""纯业务计算：游戏日、时长、战绩排序键与会员/勇士等级公式。"""

from datetime import datetime, timedelta


# ================= 数据处理 =================
def get_game_date(utc_str, tz, start_hour):
    """按 start_hour 点为界划分游戏日，返回 YYYY-MM-DD"""
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(tz)
    if dt.hour < start_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def local_time_str(utc_str, tz):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(sec):
    m, s = divmod(int(sec or 0), 60)
    return f"{m}:{s:02d}"


# ================= 战绩表排序键 =================
def _difficulty_sort_key(r):
    """N1~N8 按难度数字排，「自定义」排在数字难度之后。"""
    d = r.get("difficulty", "")
    if d.startswith("N") and d[1:].isdigit():
        return (0, int(d[1:]))
    return (1, 0)


# 用原始数值排序，不用带千分位/单位的显示字符串
SORT_KEYS = {
    "time": lambda r: r.get("time", ""),
    "difficulty": _difficulty_sort_key,
    "hero": lambda r: r.get("hero", ""),
    "duration": lambda r: r.get("durationSec", 0),
    "bp": lambda r: r.get("battlePoints", 0),
    "level": lambda r: r.get("level", 0),
    "kda": lambda r: (r.get("kills", 0) + r.get("assists", 0)) / max(r.get("deaths", 0), 1),
    "lh": lambda r: r.get("lastHits", 0),
    "gold": lambda r: r.get("gold", 0),
    "hdmg": lambda r: r.get("heroDamage", 0),
    "tdmg": lambda r: r.get("damageTaken", 0),
    "tower": lambda r: r.get("towerKills", 0),
}


# ================= 等级经验规则 =================
# 首个升级需 1000 经验，之后每升一级所需经验递增 step。
# base 是「游戏显示等级」里对应 1000 经验的那一级起点，用于和网站接口对齐：
#   会员 step=50  base=1  → 20→21 需 1950（接口 memberNextLevelPoint）
#   勇士 step=100 base=10 → 71→72 需 7100（接口 seasonNextLevelPoint）
MEMBER_STEP, MEMBER_BASE = 50, 1
WARRIOR_STEP, WARRIOR_BASE = 100, 10


def level_need(level, step, base):
    """level → level+1 所需经验"""
    return 1000 + step * (level - base)


def level_cum(level, step, base):
    """1 级 0 经验 → level 级 的累计经验"""
    n = max(0, level - 1)
    return 1000 * n + step * (n * (n + 1) // 2 - base * n)


def level_from_exp(total, step, base):
    """由累计经验反推当前等级（游戏显示口径）"""
    lv = 1
    while lv < 100000 and level_cum(lv + 1, step, base) <= total:
        lv += 1
    return lv
