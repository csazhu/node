"""App Mixin：全量同步窗口与后台同步进度。"""

import queue
import threading
import storage
from datetime import datetime
from .windows import SyncWindow


class UISyncMixin:

    # ================= 全量同步历史对局 =================
    def _show_sync_window(self):
        """顶栏「同步」：复用已开窗口，避免重复开窗。"""
        if self._closed:
            return
        if self._sync_window is not None:
            try:
                self._sync_window.lift()
                return
            except Exception:
                self._sync_window = None
        try:
            count = storage.count_matches(self.db_path, self.uid)
            last = storage.get_meta(self.db_path, "last_full_sync")
        except Exception:
            count, last = 0, ""
        self._sync_window = SyncWindow(self.root, self, count, last)

    def _start_full_sync(self):
        """后台线程按 nextPage 链拉完 history（并补 recent），逐页写库。

        子线程只往 _sync_results 入队，进度条由主线程 _poll_sync 更新（R009）。
        """
        if self._closed or self._sync_active:
            return
        self._sync_active = True
        cancel = threading.Event()
        self._sync_cancel = cancel
        win = self._sync_window
        if win is not None:
            win.set_busy()
        db_path, uid = self.db_path, self.uid
        fetcher = self.fetcher
        tz, sh = self.tz_offset, self.day_start_hour
        results = self._sync_results

        def worker():
            try:
                inserted = 0
                if cancel.is_set():
                    return
                # recent 50 场也一并入库，「全量」才名副其实
                recent = fetcher.fetch_recent()
                rms = (recent.get("matches") if isinstance(recent, dict)
                       else recent if isinstance(recent, list) else []) or []
                inserted += storage.upsert_matches(db_path, uid, rms, tz, sh)
                d = fetcher.fetch_history()
                np = d.get("nextPage") if isinstance(d, dict) else None
                total = 1 + (int(np) if np else 0)
                results.put(("progress", 0, total, "已连接，开始拉取历史对局..."))
                done = 0
                while True:
                    if cancel.is_set():
                        return
                    ms = d.get("matches") if isinstance(d, dict) else []
                    inserted += storage.upsert_matches(db_path, uid, ms, tz, sh)
                    done += 1
                    shown_total = max(total, done)
                    results.put((
                        "progress", done, shown_total,
                        f"已同步 {done}/{shown_total} 页 · 新增 {inserted} 场",
                    ))
                    np = d.get("nextPage") if isinstance(d, dict) else None
                    if np is None:
                        break
                    d = fetcher.fetch_history(page=np)
                total_count = storage.count_matches(db_path, uid)
                storage.set_meta(
                    db_path, "last_full_sync",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                results.put(("done", inserted, total_count, ""))
            except Exception as e:
                results.put(("error", str(e), 0, ""))

        threading.Thread(target=worker, daemon=True, name="full-sync").start()
        self.root.after(30, self._poll_sync)

    def _poll_sync(self):
        """主线程轮询同步事件：进度 / 完成 / 失败；窗口关了也继续收尾。"""
        if self._closed:
            return
        win = self._sync_window
        finished = False
        while True:
            try:
                kind, a, b, msg = self._sync_results.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if win is not None:
                    win.set_progress(a, b, msg)
            elif kind == "done":
                finished = True
                self._sync_active = False
                if win is not None:
                    win.set_done(a, b)
                self._refresh_from_db(force=True)
            elif kind == "error":
                finished = True
                self._sync_active = False
                if win is not None:
                    win.set_error(a)
        if not finished and self._sync_active:
            self.root.after(30, self._poll_sync)
