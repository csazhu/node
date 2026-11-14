"""App Mixin：可抢占取数线程组、结果轮询、自动刷新开关与按钮特效。"""

import json
import queue
import threading
import storage
from datetime import datetime
from .config import FETCH_MAX_ATTEMPTS, FETCH_RETRY_INTERVAL_S, FETCH_SPIN_MS, PREF_AUTO_REFRESH
from .network import FetchCancelled, fetch_with_retry


class UIFetchMixin:

    # ================= 手动刷新 / 自动刷新开关 =================
    def refresh(self):
        """手动刷新：立刻启动一组新线程抓数据；本组未结束前重复点击无效。

        不等待 5 秒定时器：若此刻有一组自动轮在途，新组会抢占它（旧组 cancel
        置位、旧结果按 seq 丢弃），保证点击后立刻重新取数。
        """
        if self._closed or self._manual_busy:
            return
        self._begin_fetch(manual=True)

    def _load_auto_refresh_pref(self):
        """读取自动刷新开关的持久化状态；库不可读或没记过则用 config 默认值。"""
        fallback = bool(int(self.cfg.get("autoRefresh", 0) or 0))
        try:
            saved = storage.get_meta(self.db_path, PREF_AUTO_REFRESH, None)
        except Exception:
            return fallback
        if saved in ("0", "1"):
            return saved == "1"
        return fallback

    def _save_auto_refresh_pref(self, enabled):
        """即时落盘：库不可写时静默跳过，不影响本次开关是否生效。"""
        try:
            storage.set_meta(self.db_path, PREF_AUTO_REFRESH, "1" if enabled else "0")
        except Exception:
            pass

    def _on_auto_toggle(self):
        """勾选才启用 5 秒自动刷新；取消勾选立即取消待触发的定时器，
        并把本次选择写进本地库，供下次启动沿用（R005）。"""
        if self._closed:
            return
        on = bool(self.auto_var.get())
        self.ctrl.set_enabled(on)
        self._save_auto_refresh_pref(on)

    # ---------- 刷新中特效：只在手动刷新的那组线程在途时显示 ----------
    _SPIN_FRAMES = ("◐", "◓", "◑", "◒")

    def _set_refresh_label(self, text):
        btn = getattr(self, "btn_refresh", None)
        if btn is None or self._closed:
            return
        try:
            btn.config(text=text)
        except Exception:
            pass  # 窗口销毁过程中不再碰控件

    def _start_spin(self):
        self._stop_spin()
        self._spin_active = True
        self._spin_idx = 0
        self._tick_spin()

    def _tick_spin(self):
        if self._closed or not self._spin_active:
            return
        frame = self._SPIN_FRAMES[self._spin_idx % len(self._SPIN_FRAMES)]
        self._spin_idx += 1
        self._set_refresh_label(f"{frame} 刷新中")
        self._spin_timer = self.root.after(FETCH_SPIN_MS, self._tick_spin)

    def _stop_spin(self):
        self._spin_active = False
        if self._spin_timer is not None:
            try:
                self.root.after_cancel(self._spin_timer)
            except Exception:
                pass
            self._spin_timer = None
        self._set_refresh_label("刷新")

    def _begin_fetch(self, manual=False):
        """启动一组取数线程：3 接口各一线程并行，成功即止，失败最多 5 次、间隔 0.5s。

        手动刷新会抢占上一组：旧组 cancel 置位后旧线程快速退出、旧结果按 seq 丢弃，
        新组立即开跑；自动轮若撞上在途的一组则跳过并重排定时器，保证不并发堆叠。
        子线程只入队结果，所有界面操作仍由主线程 _poll_results 完成（R009）。
        """
        if self._closed:
            return
        if manual:
            if self._manual_busy:
                return
        elif self._fetch_busy:
            # 有组在途（多为一组手动刷新）：自动轮不叠加，在途那轮收尾会重排
            self.ctrl.finished()
            return

        self._maybe_refresh_version()

        # 作废旧组，开新组：seq 用于丢弃旧结果，cancel 用于让旧线程立刻退出
        self._round_cancel.set()
        cancel = threading.Event()
        self._round_cancel = cancel
        self._fetch_seq += 1
        seq = self._fetch_seq
        self._fetch_busy = True
        if manual:
            self._manual_busy = True
            self._start_spin()

        self._round = {
            "seq": seq, "ranking": None, "info": None, "recent": None,
            "warnings": [], "failed": set(), "done": 0, "changed": False,
        }
        if not self._rendered_once:
            if not str(self.lbl_status.cget("text")).startswith("用户"):
                self.lbl_status.config(text="正在加载数据...")

        max_attempts = int(self.cfg.get("fetchMaxAttempts", FETCH_MAX_ATTEMPTS))
        retry_s = float(self.cfg.get(
            "fetchRetryIntervalMs", FETCH_RETRY_INTERVAL_S * 1000)) / 1000
        specs = (
            ("ranking", self.fetcher.fetch_ranking, "排行榜"),
            ("info", self.fetcher.fetch_info, "会员/赛季资料"),
            ("recent", self.fetcher.fetch_recent, "近期战绩"),
        )
        threads = []
        self._round_threads = threads

        def worker(k, f, lab):
            """单接口线程：重试到成功或次数用尽；组结束/被抢占即 return，线程随之关闭。

            所有接口（排行榜 / 会员赛季资料 / 近期战绩）都在此线程里异步写入 SQLite，
            只把「是否变化(changed)/新增条数(inserted)」的轻量标记带回主线程，
            主线程据此决定是否重绘界面（详见 R060）。
            """
            try:
                try:
                    res, err = fetch_with_retry(f, cancel, max_attempts, retry_s)
                except FetchCancelled:
                    return
                if cancel.is_set() or self._closed:
                    return
                if err or res is None:
                    self._results.put((k, res, err, lab, seq))
                    return
                try:
                    if k == "ranking":
                        # 排行榜：整包响应异步写库，返回内容是否变化
                        changed = storage.save_snapshot(
                            self.db_path, self.uid, "ranking",
                            json.dumps(res, ensure_ascii=False, separators=(",", ":")),
                        )
                        res = {"__db_written__": True, "changed": changed}
                    elif k == "info":
                        # 会员/赛季资料：整包响应异步写库，返回内容是否变化
                        changed = storage.save_snapshot(
                            self.db_path, self.uid, "info",
                            json.dumps(res, ensure_ascii=False, separators=(",", ":")),
                        )
                        res = {"__db_written__": True, "changed": changed}
                    elif k == "recent":
                        # 近期战绩：写库后只回新增条数，大对象留库里不回主线程
                        matches = res if isinstance(res, list) else (
                            res.get("matches") if isinstance(res, dict) else None) or []
                        inserted = storage.upsert_matches(
                            self.db_path, self.uid, matches,
                            self.tz_offset, self.day_start_hour,
                        )
                        res = {"__db_written__": True, "inserted": inserted}
                except Exception as e:
                    err = f"写库失败：{e}"
                self._results.put((k, res, err, lab, seq))
            finally:
                try:
                    threads.remove(threading.current_thread())
                except ValueError:
                    pass

        for key, fn, label in specs:
            t = threading.Thread(
                target=worker, args=(key, fn, label), daemon=True,
                name=f"fetch-{key}-{seq}",
            )
            threads.append(t)
            t.start()
        # 首次轮询也交回事件循环：子线程只入队，主线程异步取回；顺带保证
        # 首轮「正在加载数据...」不会在 _begin_fetch 内被同步清掉。
        self.root.after(20, lambda s=seq: self._poll_results(s))

    def _poll_results(self, seq=None):
        """主线程轮询：一次排空队列，只认当前有效组 seq，旧组结果直接丢弃。"""
        if self._closed:
            return
        if seq is None:
            seq = self._fetch_seq
        if seq != self._fetch_seq or self._round is None:
            return  # 本组已被抢占：停掉这条轮询链，避免两条链重复计数
        while True:
            try:
                key, res, err, label, rseq = self._results.get_nowait()
            except queue.Empty:
                break
            if rseq != seq:
                continue  # 旧组残留结果，丢弃
            r = self._round
            r[key] = res
            if err:
                r["warnings"].append(f"{label} 请求失败（{err.split(':', 1)[0]}）")
                r["failed"].add(label)
            else:
                handler = getattr(self, f"_on_data_{key}", None)
                if handler:
                    handler(res)
            r["done"] += 1
            if r["done"] >= 3:
                self._finish_round()
                return
        self.root.after(20, lambda s=seq: self._poll_results(s))

    # ---------- 各接口独立处理：读库 + 按变化重绘 ----------
    def _on_data_ranking(self, payload):
        """排行榜：取数线程已写库；这里只按 changed 决定是否重绘。

        payload 为写库标记（含 changed）时从库读取最新排名；测试/兜底路径
        直接传入原始 dict，兼容 render() 旧调用。
        """
        if payload is None:
            return
        if isinstance(payload, dict) and payload.get("__db_written__"):
            if not payload.get("changed", True):
                return  # 库内容未变，不重绘（无感知刷新）
            raw = storage.load_snapshot(self.db_path, self.uid, "ranking")
            if not raw:
                return
            try:
                ranking = json.loads(raw)
            except Exception:
                return
        else:
            ranking = payload  # 测试/兜底：直接给 dict
        if not isinstance(ranking, dict):
            return
        new_rank = ranking.get("rank", "-")
        if new_rank != self._last_rank or not self._rendered_once:
            self.profile["rank"] = new_rank
            self._last_rank = new_rank
            self._render_cards()
            if self._round is not None:
                self._round["changed"] = True

    def _info_fields(self, info):
        """从会员/赛季资料原始响应抽取需要展示与计算的字段（与接口字段一一对应）。"""
        return {
            "seasonLevel": info.get("seasonLevel"),
            "seasonNeed": (
                (info.get("seasonNextLevelPoint") or 0) - (info.get("seasonCurrrentLevelPoint") or 0)
                if info.get("seasonLevel") is not None else None
            ),
            "memberLevel": info.get("memberLevel"),
            "memberNeed": (
                (info.get("memberNextLevelPoint") or 0) - (info.get("memberCurrentLevelPoint") or 0)
                if info.get("memberLevel") is not None else None
            ),
            "matchCount": info.get("matchCount"),
            "winCount": info.get("winCount"),
            "memberPointTotal": info.get("memberPointTotal") or 0,
            "memberCurrPoint": info.get("memberCurrentLevelPoint") or 0,
            "memberNextPoint": info.get("memberNextLevelPoint") or 0,
            "seasonPointTotal": info.get("seasonPointTotal") or 0,
            "seasonCurrPoint": info.get("seasonCurrrentLevelPoint") or 0,
            "seasonNextPoint": info.get("seasonNextLevelPoint") or 0,
        }

    def _on_data_info(self, payload):
        """会员/赛季资料：取数线程已写库；这里只按 changed 决定是否重绘。

        读库拿到的原始响应字段保持 camelCase 口径不变；测试/兜底路径直接
        传入 profile dict（与 build_profile 输出字段同名）兼容 render()。
        """
        if payload is None:
            return
        if isinstance(payload, dict) and payload.get("__db_written__"):
            if not payload.get("changed", True):
                return  # 库内容未变，不重绘（无感知刷新）
            raw = storage.load_snapshot(self.db_path, self.uid, "info")
            if not raw:
                return
            try:
                info = json.loads(raw)
            except Exception:
                return
        else:
            info = payload  # 测试/兜底：直接给 dict
        if not isinstance(info, dict):
            return
        fields = self._info_fields(info)
        if fields != self._last_info_fields or not self._rendered_once:
            self.profile.update(fields)
            self._last_info_fields = fields
            self._render_cards()
            self._render_member_table()
            self._on_self_toggle(keep_manual=True)
            if self._round is not None:
                self._round["changed"] = True

    def _on_data_recent(self, recent):
        """近期战绩写库后只回新增条数；这里按是否有新插入决定是否刷新界面。

        库内对局无新增/更新则不刷新（无感知刷新），只有插入条数 > 0 才从库重读重绘。
        """
        if not isinstance(recent, dict):
            return
        if recent.get("inserted", 0) == 0:
            return
        self._refresh_from_db()

    def _refresh_from_db(self, force=False):
        """界面唯一数据源：战绩明细 / 每日统计 / 每月统计一律读库。

        库内签名未变且已渲染过则跳过，保证自动刷新无感知（R010）。下拉框切范围
        或全量同步结束时传 force=True 强制重算。
        """
        if self._closed:
            return
        try:
            sig = storage.stats_signature(self.db_path, self.uid)
            if not force and sig == self._last_db_sig and self._rows_rendered:
                return
            self._last_db_sig = sig
            matches = storage.fetch_matches(self.db_path, self.uid)
            rows, _, avg = self.fetcher.derive_rows_days({"matches": matches})
            days = storage.daily_stats(
                self.db_path, self.uid, self.task_points, days=None
            )
            months = storage.monthly_stats(self.db_path, self.uid, self.task_points)
        except Exception:
            return  # 读库失败保留上一轮内容，下一轮再试
        self._apply_recent_data(rows, days, avg, months)

    def _apply_recent_data(self, rows, days, avg, months=None):
        """库内聚合结果的统一落盘：独立比对后只重绘变动区块。"""
        rows_changed = (rows != self.rows)
        days_changed = (days != self.days)
        months_changed = months is not None and (months != self.months)
        if months is not None:
            self.months = months
        if (rows_changed or days_changed or months_changed
                or not self._days_rendered or not self._rows_rendered
                or not self._months_rendered):
            self.rows = rows
            self.days = days
            self.avg_duration = avg
            if days_changed or not self._days_rendered:
                self._render_days()
                self._days_rendered = True
            if months_changed or not self._months_rendered:
                self._render_months()
                self._months_rendered = True
            if rows_changed or not self._rows_rendered:
                self._refresh_hero_options()
                self.apply_filter()
                self._render_best()
                self._rows_rendered = True
            self._render_member_table()
            self._on_self_toggle(keep_manual=True)
            if self._round is not None:
                self._round["changed"] = True

    def _finish_round(self):
        """一组三接口收齐后的收尾：关掉这组线程状态、恢复按钮，再推进自动刷新。"""
        r = self._round
        self._round = None
        self._fetch_busy = False
        self._round_threads = []
        manual_done = self._manual_busy
        self._manual_busy = False
        if manual_done:
            self._stop_spin()  # 仅手动轮有特效；自动轮完全无感知，不碰按钮与状态栏
        if r is None:
            return
        try:
            # 接口失败保持静默：失败接口保留上一轮旧内容（R034）；首轮清掉
            # 「正在加载数据...」，之后自动轮不动状态栏。
            if not self._rendered_once:
                if not str(self.lbl_status.cget("text")).startswith("用户"):
                    self.lbl_status.config(text="", style="Muted.TLabel")
            # 仅在有接口真正变动时才刷新「更新于」时间戳，避免无变化时跳动
            if r["changed"]:
                self.lbl_updated.config(
                    text=f"更新于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
        finally:
            self._rendered_once = True
            if not self._closed:
                self.ctrl.finished()  # 勾上自动刷新才会安排 5 秒后的下一轮

    def _data_signature(self, data):
        """取展示内容相关的字段做比对；排除 updatedAt 等每次刷新都变的时间戳。"""
        return (
            data.get("profile"),
            data.get("rows"),
            data.get("days"),
            data.get("warnings") or [],
            data.get("failed") or [],
            data.get("avgDurationSec"),
        )

    def _data_unchanged(self, data):
        """所有接口数据与上次写入一致则视为未变：不重绘、不写入界面。"""
        sig = self._data_signature(data)
        if self._last_data_sig is not None and sig == self._last_data_sig:
            return True
        self._last_data_sig = sig
        return False

    def _finish(self, data, err):
        """刷新结束：比对后写入 / 兜底，然后安排下一轮。

        接口失败保持静默（详见 R034）：状态栏不显示失败提示、状态灯不转红，
        失败接口保留旧内容，由自动刷新下一轮重试。
        """
        if self._closed:
            return
        try:
            if data is not None:
                if self._data_unchanged(data):
                    # 数据一致：不重绘界面（不写入），仅清掉首轮加载提示
                    if not self._rendered_once:
                        self.lbl_status.config(text="")
                    self._rendered_once = True
                else:
                    self.render(data)
                    # 首轮渲染成功后清掉「正在加载数据...」提示，不显示失败信息
                    if not self._rendered_once:
                        self.lbl_status.config(text="")
                    self._rendered_once = True
            else:
                # 整轮取数失败：保持静默，状态栏不显示失败提示，等下一轮自动重试
                pass
        except Exception as e:
            self.lbl_status.config(text=f"渲染失败：{e}")
        finally:
            self.ctrl.finished()
