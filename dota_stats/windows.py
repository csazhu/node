"""独立弹窗：更新日志、发现新版本、历史对局全量同步。"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from .config import APP_VERSION
from .theme import ACCENT, ACCENT_HOVER, BG, FAINT, FONT_UI, LINE, MUTED, PANEL, S2, S3, S4, S5, TEXT, _changelog_metrics, _render_changelog
from .updater import new_changelog_entries


class ChangelogWindow(tk.Toplevel):
    """深色卡片式只读窗口：高度随内容收缩，按钮常驻底部，滚动条按需出现。"""

    WIDTH_CHARS = 80
    OUTSIDE_CLOSE_DELAY_MS = 150   # 跳过开窗瞬间的焦点抖动，避免刚弹出就自关

    def __init__(self, master, title, subtitle, entries, show_close=True,
                 close_text="关闭", headline=None, close_on_focus_out=False,
                 toggle_widget=None):
        super().__init__(master)
        self.title(title)
        self.configure(bg=BG)
        self.transient(master)
        self.resizable(False, True)
        self.minsize(480, 220)
        self._close_on_focus_out = close_on_focus_out
        self._toggle_widget = toggle_widget
        self._outside_binds = []
        self._outside_armed = False

        head = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S4, S5, S3))
        head.pack(fill="x")
        title_row = ttk.Frame(head, style="Dark.TFrame")
        title_row.pack(fill="x")
        tk.Frame(title_row, bg=ACCENT, width=3, height=20).pack(side="left", padx=(0, S2))
        ttk.Label(title_row, text=headline or title, style="Head.TLabel").pack(side="left")
        if subtitle:
            ttk.Label(head, text=subtitle, style="Muted.TLabel", wraplength=580).pack(
                anchor="w", pady=(S2, 0)
            )

        body = ttk.Frame(self, style="Dark.TFrame", padding=(S5, 0, S5, 0))
        body.pack(fill="both", expand=True)
        height, need_scroll = _changelog_metrics(entries)
        self.text = tk.Text(
            body, wrap="word", height=height, width=self.WIDTH_CHARS,
            bg=PANEL, fg=TEXT, bd=0, relief="flat",
            highlightbackground=LINE, highlightthickness=1,
            padx=S4, pady=S3, insertbackground=TEXT,
            font=(FONT_UI, 10),
        )
        self.text.tag_configure("version", foreground=ACCENT,
                                font=(FONT_UI, 11, "bold"), spacing1=6)
        self.text.tag_configure("date", foreground=FAINT,
                                font=(FONT_UI, 9))
        self.text.tag_configure("item", lmargin1=4, lmargin2=24,
                                spacing1=2, spacing3=5)
        self.text.tag_configure("bullet", foreground=ACCENT)
        self.text.tag_configure("blank", spacing1=0, spacing3=0,
                                font=(FONT_UI, 4))
        self.sb = ttk.Scrollbar(
            body, orient="vertical", command=self.text.yview,
            style="Dark.Vertical.TScrollbar"
        )
        self.text.configure(yscrollcommand=self.sb.set)
        if need_scroll:
            self.sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        _render_changelog(self.text, entries)

        self.action_bar = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S3, S5, S4))
        self.action_bar.pack(fill="x")
        self.btn_close = None
        if show_close:
            self.btn_close = ttk.Button(
                self.action_bar, text=close_text, command=self.destroy, style="Ghost.TButton"
            )
            self.btn_close.pack(side="right")
        self._center_on_master()
        if close_on_focus_out:
            # 「更新日志」是纯查看窗口，点窗口外任意位置即关闭；「发现新版本」
            # 带下载操作，保持原行为，避免误点打断更新。
            self.after(self.OUTSIDE_CLOSE_DELAY_MS, self._arm_outside_close)

    def _arm_outside_close(self):
        """延迟绑定：FocusOut 覆盖切到别的应用/桌面，主窗口点击作为兜底。"""
        try:
            if not self.winfo_exists():
                return
            self._outside_armed = True
            self._track_bind(self, "<FocusOut>", self._on_focus_out)
            self._track_bind(self.master, "<ButtonPress-1>", self._on_master_press)
        except tk.TclError:
            pass  # 窗口已被用户关掉

    def _track_bind(self, widget, sequence, func):
        before = widget.bind(sequence)
        funcid = widget.bind(sequence, func, add="+")
        # 记下本次追加的脚本片段：tkinter 的 unbind(seq, funcid) 会清掉该 widget
        # 上这个事件的全部绑定，主窗口上不能这么用，只能精确摘除自己那一段。
        added = widget.bind(sequence)[len(before):]
        self._outside_binds.append((widget, sequence, funcid, added))

    def _on_focus_out(self, event=None):
        # 焦点切换过程中 focus_get() 可能短暂为空，等事件处理完再判断是否真的离开
        self.after_idle(self._close_if_focus_left)

    def _on_master_press(self, event=None):
        if event is not None and self._toggle_widget is not None \
                and event.widget is self._toggle_widget:
            return  # 点的是「更新日志」按钮本身，交给按钮命令复用窗口
        self.after_idle(self._close_if_click_outside, event)

    def _close_if_click_outside(self, event):
        """主窗口内任意组件（排行榜卡片/表头/按钮…）被点击即关闭；窗口内点击不关。

        用点击目标的组件层级判断，而非焦点——ttk 标签、卡片默认不抢焦点，
        点它们时焦点仍停留在更新日志窗口，单纯看焦点会误判成「窗口内」而关不掉。
        """
        if not self._outside_armed:
            return
        try:
            if not self.winfo_exists():
                return
            widget = event.widget if event is not None else None
            if widget is self._toggle_widget:
                return
            w = widget
            while w is not None:
                if w is self:
                    return  # 点的是更新日志窗口内部，不关闭
                w = getattr(w, "master", None)
            self.destroy()
        except tk.TclError:
            pass

    def _close_if_focus_left(self):
        """焦点已不在本窗口（含整个应用失焦）时关闭；窗口内切换焦点不关。"""
        if not self._outside_armed:
            return
        try:
            if not self.winfo_exists():
                return
            focus = self.focus_get()
            if focus is self._toggle_widget and self._toggle_widget is not None:
                return
            if focus is None:
                self.destroy()
                return
            widget = focus
            while widget is not None:
                if widget is self:
                    return
                widget = getattr(widget, "master", None)
            self.destroy()
        except tk.TclError:
            pass

    def destroy(self):
        for widget, sequence, funcid, added in self._outside_binds:
            try:
                script = widget.bind(sequence)
                if added and added in script:
                    widget.bind(sequence, script.replace(added, "", 1))
                widget.deletecommand(funcid)
            except (tk.TclError, TypeError):
                pass
        self._outside_binds.clear()
        self._outside_armed = False
        super().destroy()

    def _center_on_master(self):
        """相对主窗口居中；请求尺寸不依赖窗口是否已映射。"""
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = self.master.winfo_rootx() + (self.master.winfo_width() - w) // 2
            y = self.master.winfo_rooty() + (self.master.winfo_height() - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass


class UpdateWindow(ChangelogWindow):
    """非模态提示窗：可随时关闭，关闭后照常使用当前版本，绝不强制更新。"""

    def __init__(self, master, app, info):
        self._info = info
        self.app = app
        entries = new_changelog_entries(info)
        if not entries:
            entries = [{
                "version": info.get("version", "?"),
                "items": [info.get("notes") or "请前往下载页查看本次更新内容。"],
            }]
        super().__init__(
            master,
            title="发现新版本",
            headline=f"v{APP_VERSION}   →   v{info.get('version', '?')}",
            subtitle="有新版本可用，可关闭本窗口继续使用当前版本，不会强制更新",
            entries=entries,
            show_close=False,
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.pbar = ttk.Progressbar(
            self, style="Update.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        self.lbl_state = ttk.Label(self.action_bar, text="", style="Muted.TLabel")
        self.lbl_state.pack(side="left", padx=(0, 10))
        self.btn_update = tk.Button(
            self.action_bar, text="立即更新", command=self._on_update,
            bg=ACCENT, fg=BG, activebackground=ACCENT_HOVER, activeforeground=BG,
            disabledforeground=MUTED, relief="flat", bd=0, padx=S4, pady=5,
            font=(FONT_UI, 10, "bold"), cursor="hand2",
        )
        self.btn_update.pack(side="right", padx=(0, 8))
        self.btn_later = ttk.Button(
            self.action_bar, text="稍后再说", command=self.destroy, style="Update.TButton"
        )
        self.btn_later.pack(side="right")

    def _on_update(self):
        self.app.start_update(self._info, self)

    def _on_restart(self):
        self.app.finish_update(self)

    def set_busy(self):
        self.btn_update.configure(state="disabled", text="正在下载...")
        self.lbl_state.configure(text="正在下载更新包...")
        self.pbar.configure(value=0)
        self.pbar.pack(fill="x", padx=18, pady=(0, 4), before=self.action_bar)

    def set_progress(self, done, total):
        if total:
            self.pbar.configure(maximum=total, value=min(done, total))
            self.lbl_state.configure(text=f"正在下载更新包... {done * 100 // total}%")
        else:
            self.lbl_state.configure(text=f"正在下载更新包... {done / 1048576:.1f} MB")

    def set_ready(self):
        self.pbar.pack_forget()
        self.btn_update.configure(state="normal", text="重启并完成更新", command=self._on_restart)
        self.lbl_state.configure(text="更新包已就绪，点击后程序将关闭并自动重启")

    def set_error(self, msg):
        self.pbar.pack_forget()
        self.btn_update.configure(state="normal", text="重试", command=self._on_update)
        self.lbl_state.configure(text=f"更新失败：{msg}")


class SyncWindow(tk.Toplevel):
    """全量同步历史对局：非模态窗口，进度条 + 完成后提示 / 失败后重新同步。"""

    def __init__(self, master, app, local_count=0, last_sync=""):
        super().__init__(master)
        self.app = app
        self.title("历史对局同步")
        self.configure(bg=BG)
        self.transient(master)
        self.resizable(False, False)
        self.minsize(520, 250)

        head = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S4, S5, S2))
        head.pack(fill="x")
        title_row = ttk.Frame(head, style="Dark.TFrame")
        title_row.pack(fill="x")
        tk.Frame(title_row, bg=ACCENT, width=3, height=20).pack(side="left", padx=(0, S2))
        ttk.Label(title_row, text="历史对局同步", style="Head.TLabel").pack(side="left")
        ttk.Label(
            head,
            text="从服务器拉取全部历史对局并写入本地 SQLite，按时间去重，重复数据不会插入",
            style="Muted.TLabel", wraplength=460,
        ).pack(anchor="w", pady=(S2, 0))

        body = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S2, S5, S2))
        body.pack(fill="x")
        self.lbl_local = ttk.Label(
            body, text=f"本地已存 {local_count} 场 · 上次全量同步：{last_sync or '从未'}",
            style="SoftMuted.TLabel",
        )
        self.lbl_local.pack(anchor="w", pady=(0, S2))
        self.pbar = ttk.Progressbar(
            body, style="Update.Horizontal.TProgressbar", mode="determinate", maximum=100,
        )
        self.lbl_state = ttk.Label(body, text="点击按钮开始同步", style="Muted.TLabel")
        self.lbl_state.pack(anchor="w")

        self.action_bar = ttk.Frame(self, style="Dark.TFrame", padding=(S5, S2, S5, S4))
        self.action_bar.pack(fill="x")
        self.btn_close = ttk.Button(
            self.action_bar, text="关闭", command=self.destroy, style="Ghost.TButton"
        )
        self.btn_close.pack(side="right")
        self.btn_sync = tk.Button(
            self.action_bar, text="全量同步历史对局", command=self._on_sync,
            bg=ACCENT, fg=BG, activebackground=ACCENT_HOVER, activeforeground=BG,
            disabledforeground=MUTED, relief="flat", bd=0, padx=S4, pady=5,
            font=(FONT_UI, 10, "bold"), cursor="hand2",
        )
        self.btn_sync.pack(side="right", padx=(0, S2))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._center_on_master(master)

    def _center_on_master(self, master):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = master.winfo_rootx() + max(0, (master.winfo_width() - w) // 2)
        y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")

    def _on_sync(self):
        self.app._start_full_sync()

    def set_busy(self):
        self.btn_sync.configure(state="disabled", text="正在同步...")
        self.lbl_state.configure(text="正在连接服务器...")
        self.pbar.configure(value=0)
        self.pbar.pack(fill="x", pady=(0, S2), before=self.lbl_state)

    def set_progress(self, done, total, msg):
        total = max(1, int(total or 1))
        self.pbar.configure(maximum=total, value=min(done, total))
        self.lbl_state.configure(text=msg)

    def set_done(self, inserted, total_count):
        self.pbar.configure(value=float(self.pbar.cget("maximum")))
        self.btn_sync.configure(state="normal", text="全量同步历史对局")
        self.lbl_state.configure(
            text=f"同步完成 · 新增 {inserted} 场 · 本地共 {total_count} 场",
            style="SoftValue.TLabel",
        )
        self.lbl_local.configure(
            text=f"本地已存 {total_count} 场 · 上次全量同步：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def set_error(self, msg):
        self.btn_sync.configure(state="normal", text="重新同步")
        self.lbl_state.configure(text=f"同步失败：{msg}", style="Error.TLabel")

    def destroy(self):
        if getattr(self.app, "_sync_window", None) is self:
            self.app._sync_window = None
        super().destroy()
