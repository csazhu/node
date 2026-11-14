"""App Mixin：版本徽章状态、版本检查队列与更新下载流程。"""

import os
import json
import queue
import sys
import threading
import time
import webbrowser
import tkinter as tk
import storage
from .config import APP_DIR, APP_VERSION, CHANGELOG, UPDATE_NEW_NAME, VERSION_CHECK_MIN_INTERVAL_MS, VERSION_URL
from .theme import BADGE_ALERT_BG, BADGE_ALERT_HOVER, BTN_HOVER, DANGER, FAINT, FONT_UI, LINE, MUTED, PANEL_SOFT, TEXT
from .updater import apply_update, download_file, fetch_version_info, is_newer
from .windows import ChangelogWindow, UpdateWindow


class UIVersionMixin:

    def _build_version_badge(self, parent):
        """右上角版本徽章：当前版本 / 服务器最新版本常驻可见，红点引导手动更新。

        不主动弹任何更新窗口；发现新版本只把徽章变红，用户点徽章才打开
        UpdateWindow。徽章用 tk 控件而非 ttk，便于逐个上色与整体点击。
        """
        self._version_state = "checking"
        self._latest_info = None
        self._badge_hover = False
        self.version_badge = tk.Frame(
            parent, bg=PANEL_SOFT, highlightbackground=LINE,
            highlightthickness=1, cursor="hand2", padx=8, pady=4,
        )
        self.version_badge.pack(side="right", padx=(8, 10))

        self.badge_widgets = []

        # 两行：当前版本 / 最新版本；标签列右对齐、版本号列左对齐，保证上下对齐。
        def mk(text, fg, font=None, row=0, column=0, sticky="w", padx=0, pady=0):
            lab = tk.Label(
                self.version_badge, text=text, fg=fg, bg=PANEL_SOFT,
                font=font or (FONT_UI, 9), bd=0, cursor="hand2",
            )
            lab.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
            self.badge_widgets.append(lab)
            return lab

        mk("当前版本", MUTED, font=(FONT_UI, 9, "bold"), row=0, column=0,
           sticky="e", padx=(0, 6), pady=(0, 2))
        self.lbl_local_version = mk(
            f"v{APP_VERSION}", TEXT, font=(FONT_UI, 10, "bold"),
            row=0, column=1, sticky="w",
        )
        mk("最新版本", MUTED, font=(FONT_UI, 9, "bold"), row=1, column=0,
           sticky="e", padx=(0, 6))
        self.lbl_remote_version = mk(
            "检查中…", MUTED, font=(FONT_UI, 10, "bold"),
            row=1, column=1, sticky="w",
        )
        self.lbl_version_dot = mk(
            " ", DANGER, font=(FONT_UI, 11, "bold"),
            row=1, column=2, sticky="w", padx=(6, 0),
        )
        self.lbl_version_action = mk(
            "", FAINT, font=(FONT_UI, 9, "bold"),
            row=1, column=3, sticky="w", padx=(2, 0),
        )
        # 固定占位宽度：检查完成、亮红点时徽章不忽宽忽窄，顶栏不跳动。
        # 边框厚度也保持恒定，警示只靠红框颜色 + 红点 + 暗红底区分。
        # 两个版本号用相同固定宽度，保证上下两行版本号框等宽、视觉严格对齐
        # （仅给「最新」加宽会让上行偏窄、下行像被缩进；宽度固定也避免状态切换时徽章抖动）。
        self.lbl_local_version.configure(width=8)
        self.lbl_remote_version.configure(width=8)
        self.lbl_version_dot.configure(width=2)
        self.lbl_version_action.configure(width=8)
        self.version_badge.configure(highlightthickness=1)

        for w in (self.version_badge, *self.badge_widgets):
            w.bind("<Button-1>", lambda e: self._on_version_click())
            w.bind("<Enter>", lambda e: self._paint_badge(True))
            w.bind("<Leave>", lambda e: self._paint_badge(False))

    def _paint_badge(self, hover):
        """悬停只换成更亮的深色底，文字保持浅色，绝不出现白底白字。"""
        self._badge_hover = hover
        if self._version_state == "update":
            bg = BADGE_ALERT_HOVER if hover else BADGE_ALERT_BG
        else:
            bg = BTN_HOVER if hover else PANEL_SOFT
        for w in (self.version_badge, *self.badge_widgets):
            w.configure(bg=bg)

    def _set_version_badge(self, state, remote_version=None):
        """主线程更新徽章：checking / latest / update / failed / off。"""
        self._version_state = state
        alert = state == "update"
        self.version_badge.configure(highlightbackground=DANGER if alert else LINE)
        if alert:
            self.lbl_remote_version.configure(text=f"v{remote_version}", fg=DANGER)
            self.lbl_version_dot.configure(text="●")
            self.lbl_version_action.configure(text="点击更新", fg=DANGER)
        else:
            self.lbl_version_dot.configure(text=" ")
            if state == "checking":
                self.lbl_remote_version.configure(text="检查中…", fg=MUTED)
                self.lbl_version_action.configure(text="", fg=FAINT)
            elif state == "failed":
                self.lbl_remote_version.configure(text="未知", fg=FAINT)
                self.lbl_version_action.configure(text="检查失败", fg=FAINT)
            elif state == "off":
                self.lbl_remote_version.configure(text="未检查", fg=FAINT)
                self.lbl_version_action.configure(text="", fg=FAINT)
            else:
                self.lbl_remote_version.configure(
                    text=f"v{remote_version or APP_VERSION}", fg=TEXT
                )
                self.lbl_version_action.configure(text="已是最新", fg=FAINT)
        self._update_version_check_button()
        self._paint_badge(self._badge_hover)

    def _update_version_check_button(self):
        """版本检查失败时才显示「重试检查」按钮，其它状态隐藏（零占位）。"""
        if self._version_state == "failed":
            if self.btn_version_check.winfo_manager() != "pack":
                self.btn_version_check.pack(side="left")
        else:
            if self.btn_version_check.winfo_manager() == "pack":
                self.btn_version_check.pack_forget()

    def _on_manual_version_check(self):
        """手动触发一次服务器版本检查（常用于自动检查失败后的重试）。"""
        if self._closed:
            return
        self.lbl_status.configure(text="正在手动检查服务器版本…")
        self._check_version(show_checking=True)

    def _on_version_click(self):
        """红点徽章是手动更新入口：点开更新窗口，其它状态只给状态栏提示。"""
        if self._closed:
            return
        if self._version_state == "update" and self._latest_info:
            self._show_update_window(self._latest_info)
        elif self._version_state == "checking":
            self.lbl_status.configure(text="正在检查服务器版本，请稍候…")
        elif self._version_state == "failed":
            # 点徽章与「重试检查」按钮同样可触发手动重试
            self._on_manual_version_check()
        else:
            self.lbl_status.configure(
                text=f"当前已是最新版本 v{APP_VERSION}，右上「更新日志」可查看历史更新"
            )

    # ---------- 版本检查与可选更新 ----------
    def start_version_check(self):
        """启动入口调用一次：先把徽章置为「检查中」，再子线程查服务器版本。"""
        self._check_version(show_checking=True)

    def _maybe_refresh_version(self):
        """自动刷新每轮静默顺带查一次版本（带最小间隔节流）。

        不把徽章置为「检查中」，避免每轮闪烁；结果回来才更新。受 checkUpdate
        开关、最小间隔、是否已有检查在途三重保护，不并发、不频繁打扰。
        """
        if self._closed or not self.cfg.get("checkUpdate", 1):
            return
        if self._version_checking:
            return
        if time.monotonic() - self._last_version_check < VERSION_CHECK_MIN_INTERVAL_MS / 1000:
            return
        self._check_version(show_checking=False)

    def _check_version(self, show_checking):
        """发起一次服务器版本检查（子线程）；show_checking 时先把徽章置为检查中。"""
        if self._closed or not self.cfg.get("checkUpdate", 1):
            self._set_version_badge("off")
            return
        if self._version_checking:
            return
        if show_checking:
            self._set_version_badge("checking")
        self._version_checking = True
        self._last_version_check = time.monotonic()
        url = self.cfg.get("versionUrl", VERSION_URL)

        def worker():
            try:
                info, err = fetch_version_info(url), None
            except Exception as e:
                info, err = None, str(e)
            if not self._closed:
                # 版本号也异步写入 SQLite：启动时可从库回填徽章，断网也能显示上次已知版本
                if info is not None:
                    try:
                        storage.save_snapshot(
                            self.db_path, "*", "version",
                            json.dumps(info, ensure_ascii=False, separators=(",", ":")),
                        )
                    except Exception:
                        pass
                self._updates.put(("version", info, err))

        threading.Thread(target=worker, daemon=True).start()
        self._ensure_update_polling()

    def _ensure_update_polling(self):
        if self._update_polling or self._closed:
            return
        self._update_polling = True
        self._poll_updates()

    def _poll_updates(self):
        """主线程轮询版本/下载事件；所有 Tk 操作都留在这里（R009）。"""
        if self._closed:
            self._update_polling = False
            return
        try:
            kind, payload, extra = self._updates.get_nowait()
        except queue.Empty:
            self.root.after(200, self._poll_updates)
            return
        handler = getattr(self, f"_on_update_{kind}", None)
        if handler:
            handler(payload, extra)
        if self._update_active:
            self.root.after(50, self._poll_updates)
        else:
            self._update_polling = False

    def _on_update_version(self, info, err):
        """只更新右上角徽章：有新版亮红点，绝不主动弹窗打扰用户。

        比对上次写入的版本状态：一致则跳过写入（避免每轮无谓重绘徽章）。
        仅当正在显示「检查中…」时（show_checking 入口）强制落地结果，
        否则徽章会卡在「检查中…」不回落。
        """
        self._update_active = False
        self._version_checking = False
        if err or not info:
            new_state, new_remote = "failed", None
        else:
            self._latest_info = info
            remote = info.get("version")
            new_state, new_remote = (
                "update" if is_newer(remote, APP_VERSION) else "latest", remote,
            )
        if self._version_state != "checking" and \
                self._last_version_state == new_state and \
                self._last_remote_version == new_remote:
            return
        self._last_version_state = new_state
        self._last_remote_version = new_remote
        self._set_version_badge(new_state, new_remote)

    def _show_update_window(self, info):
        """仅由用户点击版本徽章触发；可关闭，不强制更新。"""
        win = self._update_window
        if win is not None and win.winfo_exists():
            return
        self._update_window = UpdateWindow(self.root, self, info)

    def _show_changelog(self):
        win = self._changelog_window
        if win is not None and win.winfo_exists():
            win.lift()
            return
        self._changelog_window = ChangelogWindow(
            self.root, title="更新日志", subtitle=f"当前版本 v{APP_VERSION}", entries=CHANGELOG,
            close_on_focus_out=True, toggle_widget=self.btn_changelog,
        )

    def start_update(self, info, window=None):
        """用户点「立即更新」才触发：后台下载 exe，不阻塞界面。"""
        if self._update_active or self._closed:
            return
        url = (info or {}).get("downloadUrl")
        if not url:
            if window:
                window.set_error("版本清单缺少 downloadUrl")
            return
        # 源码运行没有 exe 可替换，降级为打开下载页手动处理。
        if not getattr(sys, "frozen", False):
            webbrowser.open((info or {}).get("releasePage") or url)
            if window:
                window.set_error("源码运行模式，请在下载页手动替换 exe")
            return
        self._update_active = True
        self._update_window = window or self._update_window
        dest = os.path.join(APP_DIR, UPDATE_NEW_NAME)
        try:
            os.remove(dest)
        except OSError:
            pass
        if window:
            window.set_busy()

        def worker():
            try:
                download_file(
                    url, dest,
                    progress=lambda d, t: self._updates.put(("progress", (d, t), None)),
                )
            except Exception as e:
                self._updates.put(("error", str(e), None))
            else:
                self._updates.put(("done", dest, None))

        threading.Thread(target=worker, daemon=True).start()
        self._ensure_update_polling()

    def _on_update_progress(self, payload, extra):
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_progress(*payload)

    def _on_update_done(self, path, extra):
        self._update_active = False
        self._new_exe = path
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_ready()

    def _on_update_error(self, msg, extra):
        self._update_active = False
        self._new_exe = None
        win = self._update_window
        if win is not None and win.winfo_exists():
            win.set_error(msg)

    def finish_update(self, window=None):
        """二次确认后写替换脚本并关窗；脚本等进程退出后覆盖 exe 并重启。"""
        if not self._new_exe or not os.path.isfile(self._new_exe):
            return
        try:
            apply_update(self._new_exe)
        except Exception as e:
            if window is not None and window.winfo_exists():
                window.set_error(f"无法启动更新脚本：{e}")
            return
        self._on_close()
