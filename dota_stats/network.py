"""网络层：HTTP / Firebase token / 业务接口取数、可抢占重试与刷新调度。"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from .config import API_BASE, API_TIMEOUT, AUTO_REFRESH_INTERVAL_MS, FETCH_MAX_ATTEMPTS, FETCH_RETRY_INTERVAL_S, TOKEN_CACHE_TTL, TOKEN_TIMEOUT, TOKEN_URL
from .domain import fmt_duration, get_game_date, local_time_str


# ================= HTTP =================
def _proxy_host():
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def _build_opener():
    """带系统代理支持的 opener"""
    proxy = _proxy_host()
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler())
    return urllib.request.build_opener(*handlers)


_opener = _build_opener()


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def http_json(url, method="GET", headers=None, data=None, timeout=API_TIMEOUT):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with _opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_id_token(refresh_token, timeout=TOKEN_TIMEOUT):
    data = http_json(
        TOKEN_URL,
        method="POST",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=timeout,
    )
    return data["id_token"]


def api_get(token, url, timeout=API_TIMEOUT):
    return http_json(url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
class DataFetcher:
    def __init__(self, cfg, heroes):
        self.cfg = cfg
        self.heroes = heroes
        self.api_timeout = float(cfg.get("apiTimeout", API_TIMEOUT))
        self.token_timeout = float(cfg.get("tokenTimeout", TOKEN_TIMEOUT))
        self._token = None
        self._token_at = 0.0

    def _get_token(self):
        """id_token 缓存 50 分钟：短间隔的重复取数没必要每次都换 token。"""
        if self._token and time.monotonic() - self._token_at < TOKEN_CACHE_TTL:
            return self._token
        try:
            token = refresh_id_token(self.cfg["refreshToken"], timeout=self.token_timeout)
        except Exception:
            # 刷新失败就丢弃旧凭证，线程内重试时重新取，别拿过期 token 把 5 次耗尽
            self._token = None
            raise
        self._token = token
        self._token_at = time.monotonic()
        return token

    # ---------- 单接口独立获取（各走各自线程，互不阻塞） ----------
    def fetch_ranking(self):
        """排行榜：单一接口独立请求，失败由调用方（collect / 刷新线程）捕获容错。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/ranking",
                      timeout=self.api_timeout)

    def fetch_info(self):
        """会员 / 赛季资料：单一接口独立请求。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/info?include=member",
                      timeout=self.api_timeout)

    def fetch_recent(self):
        """近期战绩：单一接口独立请求。"""
        token = self._get_token()
        return api_get(token, API_BASE + f"/api/player/{self.cfg['userId']}/stats/recent",
                      timeout=self.api_timeout)

    def fetch_history(self, page=None):
        """历史对局（recent 50 场之外）：默认窗口或 ?page=N 分页。"""
        token = self._get_token()
        url = API_BASE + f"/api/player/{self.cfg['userId']}/stats/history"
        if page is not None:
            url += f"?page={page}"
        return api_get(token, url, timeout=self.api_timeout)

    def derive_rows_days(self, recent):
        """把原始近期战绩聚合为战绩明细 rows 与每日统计 days（含平均时长）。

        纯计算、无网络；collect 与并行刷新线程共用同一份逻辑，保证两份路径结果一致。
        """
        matches = recent if isinstance(recent, list) else (
            recent.get("matches") if isinstance(recent, dict) else None) or []
        durations = [int(m.get("durationSec") or 0) for m in matches if m.get("durationSec")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        tz = timezone(timedelta(hours=self.cfg.get("tzOffset", 8)))
        start_hour = self.cfg.get("gameDayStartHour", 8)
        task_points = self.cfg.get("taskPoints", 300)

        # 每日统计
        by_date = {}
        for m in matches:
            if not m.get("endedAt"):
                continue
            d = get_game_date(m["endedAt"], tz, start_hour)
            e = by_date.setdefault(d, {"count": 0, "points": 0, "minutes": 0.0})
            e["count"] += 1
            e["points"] += int(m.get("battlePoints") or 0)
            e["minutes"] += (m.get("durationSec") or 0) / 60

        days = []
        for d in sorted(by_date, reverse=True):
            e = by_date[d]
            total_min = round(e["minutes"])
            h, m = divmod(total_min, 60)
            eff = (e["points"] - task_points) / (e["minutes"] / 60) if e["minutes"] else 0
            days.append(
                {
                    "date": d,
                    "count": e["count"],
                    "points": e["points"],
                    "time": f"{h}时{m}分" if h else f"{m}分",
                    "eff": eff,
                }
            )

        # 战绩明细
        rows = []
        for m in matches:
            key = (m.get("heroName") or "").replace("npc_dota_hero_", "")
            hero = self.heroes.get(key, key)
            diff = m.get("difficulty")
            rows.append(
                {
                    "time": local_time_str(m["endedAt"], tz) if m.get("endedAt") else "",
                    "difficulty": f"N{diff}" if isinstance(diff, int) and 1 <= diff <= 8 else "自定义",
                    "level": m.get("level") or 0,
                    "hero": hero,
                    "awaken": (m.get("awaken") or 0) > 0,
                    "disconnected": bool(m.get("isDisconnected")),
                    "win": bool(m.get("win")),
                    "durationText": fmt_duration(m.get("durationSec")),
                    "durationSec": int(m.get("durationSec") or 0),
                    "kills": m.get("kills") or 0,
                    "deaths": m.get("deaths") or 0,
                    "assists": m.get("assists") or 0,
                    "lastHits": m.get("lastHits") or 0,
                    "gold": m.get("totalGoldEarned") or 0,
                    "heroDamage": m.get("heroDamage") or 0,
                    "damageTaken": m.get("damageTaken") or 0,
                    "towerKills": m.get("towerKills") or 0,
                    "battlePoints": m.get("battlePoints") or 0,
                }
            )
        return rows, days, avg_duration

    def build_profile(self, ranking, info):
        """把排行榜 + 会员/赛季资料原始响应聚合为 profile 字段（供 collect 兜底用）。"""
        info = info or {}
        ranking = ranking or {}
        return {
            "rank": ranking.get("rank", "-"),
            "seasonLevel": info.get("seasonLevel"),
            "seasonNeed": (
                (info.get("seasonNextLevelPoint") or 0) - (info.get("seasonCurrrentLevelPoint") or 0)
                if info.get("seasonLevel") is not None
                else None
            ),
            "memberLevel": info.get("memberLevel"),
            "memberNeed": (
                (info.get("memberNextLevelPoint") or 0) - (info.get("memberCurrentLevelPoint") or 0)
                if info.get("memberLevel") is not None
                else None
            ),
            "matchCount": info.get("matchCount"),
            "winCount": info.get("winCount"),
            # 等级预测 / 勇士计算用原始经验值
            "memberPointTotal": info.get("memberPointTotal") or 0,
            "memberCurrPoint": info.get("memberCurrentLevelPoint") or 0,
            "memberNextPoint": info.get("memberNextLevelPoint") or 0,
            "seasonPointTotal": info.get("seasonPointTotal") or 0,
            "seasonCurrPoint": info.get("seasonCurrrentLevelPoint") or 0,
            "seasonNextPoint": info.get("seasonNextLevelPoint") or 0,
        }

    def collect(self):
        """兼容聚合入口（测试 / 兜底）：串行取三接口后聚合。

        内部仍走 fetch_* + derive/build，逻辑与并行刷新完全一致；
        各接口独立异常容错：单个失败记入 warnings/failed，由渲染层跳过该区块。
        token 失败则整体抛 RuntimeError（与单接口失败区分开）。
        """
        try:
            self._get_token()
        except Exception as e:
            self._token = None  # 凭证可能已失效，下一轮强制重新获取
            raise RuntimeError(f"登录凭证刷新失败（{type(e).__name__}）: {e}") from e

        warnings = []
        failed = set()

        def safe(fn, label):
            try:
                return fn()
            except Exception as e:
                # 单个接口失败不影响其它接口：记入失败清单，由渲染层跳过该区块更新
                warnings.append(f"{label} 请求失败（{type(e).__name__}）")
                failed.add(label)
                return None

        ranking = safe(self.fetch_ranking, "排行榜")
        info = safe(self.fetch_info, "会员/赛季资料")
        recent = safe(self.fetch_recent, "近期战绩")
        rows, days, avg_duration = self.derive_rows_days(recent)
        profile = self.build_profile(ranking, info)
        return {
            "profile": profile,
            "days": days,
            "rows": rows,
            "avgDurationSec": avg_duration,
            "warnings": warnings,
            "failed": list(failed),
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class FetchCancelled(Exception):
    """所属线程组已被新一组抢占或窗口已关闭：立刻放弃取数，不再入队结果。"""


def fetch_with_retry(fn, cancel, max_attempts=FETCH_MAX_ATTEMPTS,
                     retry_s=FETCH_RETRY_INTERVAL_S):
    """单接口取数：成功即返回 (data, None)，失败最多尝试 max_attempts 次。

    每次失败后等 retry_s 秒再试；取消事件置位时立即唤醒并抛 FetchCancelled，
    「旧组被抢占」时旧线程不必等满间隔就退出。用尽次数仍失败返回 (None, 最后一次错误)。
    cancel 为 threading.Event，由所属线程组持有。
    """
    limit = max(1, int(max_attempts))
    last_err = None
    for attempt in range(1, limit + 1):
        if cancel is not None and cancel.is_set():
            raise FetchCancelled()
        try:
            return fn(), None
        except Exception as e:  # 网络 / 解析异常都算一次失败，交给下一次尝试
            last_err = f"{type(e).__name__}: {e}"
            if attempt >= limit:
                break
            if cancel is not None:
                if cancel.wait(retry_s):  # 被抢占/关窗时不再等满 0.5 秒
                    raise FetchCancelled()
            elif retry_s > 0:
                time.sleep(retry_s)
    return None, last_err


# ================= 自动刷新调度 =================
class RefreshController:
    """纯逻辑调度器（不依赖 tkinter）：一次刷新完成后等 interval_ms 再发起下一轮。

    after / after_cancel 由外部注入，便于无 GUI 自测：
      tkinter -> root.after / root.after_cancel；测试 -> 记录延迟的假时钟。
    """

    def __init__(self, after, after_cancel, start_refresh, interval_ms=AUTO_REFRESH_INTERVAL_MS):
        self._after = after
        self._after_cancel = after_cancel
        self._start_refresh = start_refresh
        self.interval_ms = int(interval_ms)
        self.enabled = True
        self.running = False
        self.stopped = False
        self.rounds = 0
        self._timer = None

    def _cancel_timer(self):
        if self._timer is not None:
            try:
                self._after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

    def schedule(self, delay_ms=None):
        """安排下一轮；已有定时器会被重置。返回是否成功安排。"""
        if self.stopped or not self.enabled or self.running:
            return False
        self._cancel_timer()
        delay = self.interval_ms if delay_ms is None else int(delay_ms)
        self._timer = self._after(delay, self.tick)
        return True

    def tick(self):
        """定时器到期：发起一轮刷新。"""
        self._timer = None
        if self.stopped or not self.enabled:
            return False
        return self.request()

    def request(self):
        """立即发起一轮（手动按钮与自动 tick 共用）；刷新中或已停止则忽略。"""
        if self.stopped or self.running:
            return False
        self._cancel_timer()
        self.running = True
        self.rounds += 1
        try:
            self._start_refresh()
        except Exception:
            self.running = False
            raise
        return True

    def finished(self):
        """一轮刷新结束（成功或失败）：重新安排 5 秒后的下一轮。"""
        if self.stopped:
            return False
        self.running = False
        return self.schedule()

    def set_enabled(self, enabled):
        """自动刷新开关；关闭时取消待触发的定时器，打开时立即开始一轮。"""
        self.enabled = bool(enabled)
        if not self.enabled:
            self._cancel_timer()
            return False
        if not self.running:
            return self.schedule(0)
        return False

    def stop(self):
        """窗口关闭：不再发起任何新请求或定时器。"""
        self.stopped = True
        self._cancel_timer()
