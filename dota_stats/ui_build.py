"""App Mixin：主窗口骨架、顶栏、表格与版本徽章的构建。"""

import tkinter as tk
from tkinter import ttk
from .theme import ACCENT, ACCENT_HOVER, ACCENT_SOFT, BG, BTN_HOVER, BTN_PRESSED, DANGER, FAINT, FONT_NUM, FONT_UI, LINE, MUTED, PANEL, PANEL_SOFT, S1, S2, S3, S4, S5, TEXT, _divider


class UIBuildMixin:

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        # 表面：三层亮度建立层级，越靠上越亮；区块之间只用 1px 细线分隔
        style.configure("Dark.TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("Soft.TFrame", background=PANEL)
        style.configure("Day.TFrame", background=PANEL_SOFT)
        # 排版：标题 / 正文 / 辅助 三级，指标数值单独一级，不用大图标堆砌
        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 10))
        style.configure("Head.TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 16, "bold"))
        style.configure("Subhead.TLabel", background=BG, foreground=TEXT, font=(FONT_UI, 12, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("Faint.TLabel", background=BG, foreground=FAINT, font=(FONT_UI, 9))
        style.configure("Error.TLabel", background=BG, foreground=DANGER, font=(FONT_UI, 9))
        style.configure("Chip.TLabel", background=PANEL_SOFT, foreground=MUTED,
                        font=(FONT_UI, 9), padding=(7, 3))
        # 排序提示：未排序=中性灰提示；排序中=强调色高亮，随点击切换、醒目
        style.configure("SortActive.TLabel", background=ACCENT_SOFT, foreground=ACCENT,
                        font=(FONT_UI, 9, "bold"), padding=(7, 3))
        style.configure("CardLabel.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("CardValue.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 24, "bold"))
        style.configure("CardSub.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        # 概览卡「距下一级还差 X」中的数值：放大并改用唯一强调色，形成关键焦点
        style.configure("CardSubNum.TLabel", background=PANEL, foreground=ACCENT,
                        font=(FONT_NUM, 14, "bold"))
        style.configure("Section.TLabel", background=BG, foreground=MUTED, font=(FONT_UI, 10, "bold"))
        style.configure("DayHead.TLabel", background=PANEL_SOFT, foreground=MUTED, font=(FONT_UI, 9, "bold"))
        style.configure("DayCell.TLabel", background=PANEL, foreground=TEXT, font=(FONT_NUM, 11))
        style.configure("DayCellNeg.TLabel", background=PANEL, foreground=DANGER, font=(FONT_NUM, 11))
        style.configure("TEntry", fieldbackground=PANEL_SOFT, foreground=TEXT,
                        insertbackground=ACCENT, borderwidth=1, padding=(6, 4))
        style.configure("Update.TButton", padding=(12, 5))
        style.configure(
            "Update.Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL_SOFT,
            bordercolor=PANEL_SOFT, lightcolor=ACCENT, darkcolor=ACCENT,
        )
        # 按钮层级：Filled(Primary) > Ghost > Text；次要操作一律不加实心底
        style.configure("TButton", background=PANEL_SOFT, foreground=TEXT,
                        borderwidth=0, padding=(14, 6), font=(FONT_UI, 10))
        style.configure("Primary.TButton", background=ACCENT, foreground=BG,
                        borderwidth=0, padding=(18, 7), font=(FONT_UI, 10, "bold"))
        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                        borderwidth=1, relief="solid", bordercolor=LINE,
                        padding=(12, 6), font=(FONT_UI, 10))
        # clam 默认把 TButton 的 active 背景映射成近白色 #eeebe7，而界面文字是
        # 浅色 TEXT；只 configure 改不掉状态映射，悬停就会白底白字。这里把
        # active / pressed / disabled 的背景与前景成对覆盖，保证任何状态都可读。
        btn_bg = [("disabled", PANEL_SOFT), ("pressed", BTN_PRESSED), ("active", BTN_HOVER)]
        btn_fg = [("disabled", FAINT), ("pressed", TEXT), ("active", TEXT)]
        for btn_style in ("TButton", "Update.TButton", "Ghost.TButton"):
            style.map(
                btn_style,
                background=btn_bg,
                foreground=btn_fg,
                bordercolor=[("active", LINE)],
                lightcolor=[("active", BTN_HOVER), ("pressed", BTN_PRESSED)],
                darkcolor=[("active", BTN_HOVER), ("pressed", BTN_PRESSED)],
            )
        style.map(
            "Primary.TButton",
            background=[("disabled", PANEL_SOFT), ("pressed", BTN_PRESSED), ("active", ACCENT_HOVER)],
            foreground=[("disabled", FAINT), ("pressed", BG), ("active", BG)],
        )
        # 左侧两个面板与卡片同底色，避免「卡片套卡片」的廉价层次
        style.configure("Soft.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 10))
        style.configure("SoftMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT_UI, 9))
        style.configure("SoftHead.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 11, "bold"))
        style.configure("SoftValue.TLabel", background=PANEL, foreground=ACCENT, font=(FONT_UI, 11, "bold"))
        style.configure("SoftResult.TLabel", background=PANEL, foreground=TEXT, font=(FONT_UI, 11, "bold"))
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"Dark.{orient}.TScrollbar", background=LINE, troughcolor=BG,
                bordercolor=BG, arrowcolor=MUTED, relief="flat", arrowsize=8,
            )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", PANEL), ("readonly", PANEL)],
            foreground=[("disabled", FAINT)],
            bordercolor=[("focus", ACCENT), ("hover", LINE)],
        )
        # 下拉框：深色面 + 浅色字；只读态（难度筛选）同样浅字，避免白底白字
        style.configure(
            "TCombobox", fieldbackground=PANEL_SOFT, background=PANEL_SOFT,
            foreground=TEXT, arrowcolor=MUTED, borderwidth=1, padding=(6, 4),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("focus", PANEL_SOFT), ("readonly", PANEL_SOFT)],
            foreground=[("readonly", TEXT), ("disabled", FAINT)],
            bordercolor=[("focus", ACCENT), ("hover", LINE)],
        )

        # 每日 / 每月统计 tab：clam 的 Notebooks 默认浅底，选中/悬停必须成对覆盖，
        # 否则深色界面里会出现白底浅字（R025）。
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=PANEL_SOFT, foreground=MUTED,
                        padding=(S4, S2), borderwidth=0, font=(FONT_UI, 10))
        style.map(
            "TNotebook.Tab",
            background=[("selected", PANEL), ("active", BTN_HOVER), ("disabled", PANEL_SOFT)],
            foreground=[("selected", ACCENT), ("active", TEXT), ("disabled", FAINT)],
        )

        # 先配置好两种表格样式，再创建控件
        self._style_tree(None, big=False)
        self._style_tree(None, big=True)

        # ---------- 应用头：左侧品牌与同步时间，右侧操作按主/次分层 ----------
        top = ttk.Frame(self.root, style="Dark.TFrame")
        top.pack(fill="x", padx=S5, pady=(S4, S3))
        tk.Frame(top, bg=ACCENT, width=3, height=38).pack(side="left", padx=(0, S3))
        brand = ttk.Frame(top, style="Dark.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="10v10AI 数据面板", style="Head.TLabel").pack(anchor="w")
        meta = ttk.Frame(brand, style="Dark.TFrame")
        meta.pack(anchor="w", pady=(2, 0))
        self.lbl_updated = ttk.Label(meta, text="", style="Muted.TLabel")
        self.lbl_updated.pack(side="left")
        ttk.Label(meta, text="  ·  个人战绩实时同步", style="Faint.TLabel").pack(side="left")
        # 先 pack 的靠右：更新日志在最右上角，旁边是版本徽章（当前版本 +
        # 服务器最新版本常驻可见，有新版才亮红点，由用户手动点开更新）。
        self.btn_changelog = ttk.Button(
            top, text="更新日志", style="Ghost.TButton", command=self._show_changelog
        )
        self.btn_changelog.pack(side="right")
        # 版本检查失败时出现的「重试检查」按钮：固定在徽章右侧，平时隐藏不占位
        # （外层 frame 始终占位在一处，仅内部按钮显隐，避免顶栏跳动或 pack 重排错位）。
        self._version_check_frame = ttk.Frame(top, style="Dark.TFrame")
        self._version_check_frame.pack(side="right", padx=(0, S2))
        self.btn_version_check = ttk.Button(
            self._version_check_frame, text="重试检查", style="Ghost.TButton",
            command=self._on_manual_version_check,
        )
        self.btn_version_check.pack_forget()  # 默认隐藏，_set_version_badge 在失败时显示
        self._build_version_badge(top)
        # 「同步」入口：点开非模态窗口执行全量历史对局同步
        self.btn_sync = ttk.Button(
            top, text="同步", style="Ghost.TButton", command=self._show_sync_window
        )
        self.btn_sync.pack(side="right", padx=(0, S2))
        # 手动刷新按钮 + 自动刷新开关：按钮在上，小字勾选行在按钮左下方（左对齐），
        # 默认不勾（autoRefresh=0）；勾上才由 RefreshController 每 5 秒续跑一轮。
        # 按钮固定 width，避免「刷新」↔「◐ 刷新中」切换时顶栏宽度跳动（R026）。
        refresh_box = ttk.Frame(top, style="Dark.TFrame")
        refresh_box.pack(side="right", padx=(0, S4))
        self.btn_refresh = ttk.Button(
            refresh_box, text="刷新", style="Primary.TButton", width=10,
            command=self.refresh,
        )
        self.btn_refresh.pack(anchor="e")
        auto_row = ttk.Frame(refresh_box, style="Dark.TFrame")
        auto_row.pack(anchor="w", pady=(S1, 0))
        self.auto_chk = tk.Checkbutton(
            auto_row,
            text="自动刷新",
            variable=self.auto_var,
            command=self._on_auto_toggle,
            bg=BG,
            fg=MUTED,
            selectcolor=ACCENT_SOFT,
            activebackground=BG,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=(FONT_UI, 9),
        )
        self.auto_chk.pack(side="left")
        _divider(self.root)  # 应用头与内容之间的通栏细线

        # 概览指标：一整块面板 + 卡片间 1px 竖线，避免四个悬浮方块
        self.cards_frame = tk.Frame(
            self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1
        )
        self.cards_frame.pack(fill="x", padx=S5, pady=(S3, S3))
        for i in range(4):
            self.cards_frame.columnconfigure(i, weight=1, uniform="card")

        # 启动时即固定 4 张概览卡骨架并预留副文本行高度：避免数据加载后卡片从
        # 1 张变 4 张、高度撑开导致整页跳动（R040）。数据到了只更新文字，不重建。
        self._card_slots = []
        for i, clabel in enumerate(["排行榜排名", "赛季等级", "会员等级", "总场次"]):
            f = tk.Frame(self.cards_frame, bg=PANEL)
            f.grid(row=0, column=i, sticky="nsew", padx=(S4, S4), pady=(S2, S2))
            tk.Frame(f, bg=ACCENT if i == 0 else LINE, height=2, width=28).pack(
                anchor="w", pady=(0, S1)
            )
            ttk.Label(f, text=clabel, style="CardLabel.TLabel").pack(anchor="w")
            value = ttk.Label(f, text="—", style="CardValue.TLabel")
            value.pack(anchor="w", pady=(S1, 0))
            sub_frame = tk.Frame(f, bg=PANEL)
            sub_frame.pack(anchor="w", pady=(S1, 0))
            sub_l = ttk.Label(sub_frame, text="", style="CardSub.TLabel")
            sub_l.pack(side="left")
            sub_r = ttk.Label(sub_frame, text="", style="CardSubNum.TLabel")
            sub_r.pack(side="left")
            if i < 3:
                # 竖分隔线放在卡片内部，避免增加 cards_frame 的直接子控件数量
                tk.Frame(f, bg=LINE, width=1).place(relx=1.0, x=8, rely=0, relheight=1.0)
            self._card_slots.append({"value": value, "sub_l": sub_l, "sub_r": sub_r})
        # 用空数据先填一次骨架，保证加载前显示「— 名 / — 级」而非光秃秃的「—」
        self._render_cards()

        # 状态栏先占底部，再让主体填满剩余空间，避免内容过高把状态栏挤出窗口
        status_bar = ttk.Frame(self.root, style="Dark.TFrame")
        status_bar.pack(side="bottom", fill="x", padx=S5, pady=(S2, S3))
        self.status_dot = tk.Label(status_bar, text="●", bg=BG, fg=FAINT, font=(FONT_UI, 8), bd=0)
        self.status_dot.pack(side="left", padx=(0, S2))
        self.lbl_status = ttk.Label(status_bar, text="正在加载...", style="Muted.TLabel")
        self.lbl_status.pack(side="left")

        # 主体：左（每日统计 / 会员表 / 勇士表）/ 右战绩
        body = ttk.Frame(self.root, style="Dark.TFrame")
        body.pack(fill="both", expand=True, padx=S5, pady=(0, S3))
        body.columnconfigure(0, minsize=480)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左列整体可滚动，新增面板不会把窗口撑爆
        left_outer = ttk.Frame(body, style="Dark.TFrame")
        left_outer.grid(row=0, column=0, sticky="nsew")
        self.left_canvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0, width=464)
        left_sb = ttk.Scrollbar(
            left_outer, orient="vertical", command=self.left_canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side="right", fill="y", padx=(S2, 0))
        self.left_canvas.pack(side="left", fill="both", expand=True)
        left = ttk.Frame(self.left_canvas, style="Dark.TFrame")
        self._left_win = self.left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfig(self._left_win, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        # ---------- 统计区：每日 / 每月两个 tab，固定预留 10 行高度 + 内部滚动 ----------
        DAY_VISIBLE_ROWS = 10
        DAY_ROW_H = 30
        self.day_cols_def = (("日期", 116), ("场次", 66), ("积分", 92), ("总耗时", 88), ("效率", 86))
        self.month_cols_def = (("月份", 116), ("场次", 66), ("积分", 92), ("总耗时", 88), ("效率", 86))
        self.stats_nb = ttk.Notebook(left)
        self.stats_nb.pack(fill="x", pady=(0, S2))
        day_tab = ttk.Frame(self.stats_nb, style="Dark.TFrame")
        month_tab = ttk.Frame(self.stats_nb, style="Dark.TFrame")
        self.stats_nb.add(day_tab, text="每日统计")
        self.stats_nb.add(month_tab, text="每月统计")

        day_head = ttk.Frame(day_tab, style="Dark.TFrame")
        day_head.pack(fill="x", pady=(0, S2))
        ttk.Label(day_head, text="按游戏日汇总 · 全部历史", style="Faint.TLabel").pack(side="left")

        month_head = ttk.Frame(month_tab, style="Dark.TFrame")
        month_head.pack(fill="x", pady=(0, S2))
        ttk.Label(month_head, text="按自然月汇总 · 全部历史", style="Faint.TLabel").pack(side="left")

        def build_stats_table(parent, cols_def):
            wrap = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            wrap.pack(fill="x")
            head_row = ttk.Frame(wrap, style="Day.TFrame")
            head_row.pack(fill="x")
            for i, (text, w) in enumerate(cols_def):
                head_row.columnconfigure(i, minsize=w)
                tk.Label(
                    head_row, text=text, bg=PANEL_SOFT, fg=MUTED,
                    font=(FONT_UI, 10, "bold"), anchor="center", pady=6,
                ).grid(row=0, column=i, sticky="ew")
            _divider(wrap)
            # 固定 10 行可视高度：数据从 0 到 25 天都不改变区块高度，避免整页跳动
            canvas = tk.Canvas(
                wrap, bg=PANEL, highlightthickness=0,
                height=DAY_VISIBLE_ROWS * DAY_ROW_H,
            )
            sb = ttk.Scrollbar(
                wrap, orient="vertical", command=canvas.yview,
                style="Dark.Vertical.TScrollbar",
            )
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="x", expand=True)
            rows_frame = tk.Frame(canvas, bg=PANEL)
            win_id = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
            # scrollregion 必须至少覆盖可视高度：只有 2 行数据时若仍按 bbox 原样
            # 设置，Tk 会把滚动范围撑到一屏并允许滚出大片空白（R058）。
            rows_frame.bind(
                "<Configure>",
                lambda e, c=canvas: self._sync_stats_scrollregion(c),
            )
            canvas.bind(
                "<Configure>",
                lambda e, c=canvas, w=win_id: c.itemconfig(w, width=e.width),
            )
            return canvas, rows_frame

        self.day_canvas, self.day_rows_frame = build_stats_table(day_tab, self.day_cols_def)
        self.month_canvas, self.month_rows_frame = build_stats_table(month_tab, self.month_cols_def)

        # ---------- 会员表：未来 100 级达成日期（一行 2 个，可折叠下拉 + 内部滚动） ----------
        mem_outer = tk.Frame(left, bg=LINE, padx=1, pady=1)
        mem_outer.pack(fill="x", pady=(S3, 0))
        mem_box = ttk.Frame(mem_outer, style="Soft.TFrame", padding=(S4, S2))
        mem_box.pack(fill="x")
        mem_head = ttk.Frame(mem_box, style="Soft.TFrame")
        mem_head.pack(fill="x")
        tk.Frame(mem_head, bg=ACCENT, width=3, height=18).pack(side="left", padx=(0, S2))
        self.mem_toggle = tk.Button(
            mem_head,
            text="会员等级预测（未来 100 级）  ▲",
            command=self._toggle_member,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL_SOFT,
            activeforeground=ACCENT,
            font=(FONT_UI, 11, "bold"),
            bd=0,
            relief="flat",
            anchor="w",
            cursor="hand2",
        )
        self.mem_toggle.pack(side="left")
        ttk.Label(mem_head, text="每日", style="SoftMuted.TLabel").pack(side="left", padx=(S3, S2))
        self.mem_daily = ttk.Entry(mem_head, width=6, justify="center")
        self.mem_daily.insert(0, "100")
        self.mem_daily.pack(side="left")
        self.mem_daily.bind("<KeyRelease>", lambda e: self._render_member_table())
        ttk.Label(mem_head, text="经验", style="SoftMuted.TLabel").pack(side="left", padx=(S1, 0))

        self.mem_summary = ttk.Label(mem_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.mem_summary.pack(anchor="w", pady=(S2, 0))

        self.mem_body = ttk.Frame(mem_box, style="Soft.TFrame")
        self.mem_body.pack(fill="x", pady=(S2, 0), after=self.mem_summary)
        self.mem_canvas = tk.Canvas(self.mem_body, bg=PANEL, highlightthickness=0, height=96)
        mem_sb = ttk.Scrollbar(
            self.mem_body, orient="vertical", command=self.mem_canvas.yview, style="Dark.Vertical.TScrollbar"
        )
        self.mem_canvas.configure(yscrollcommand=mem_sb.set)
        mem_sb.pack(side="right", fill="y")
        self.mem_canvas.pack(side="left", fill="x", expand=True)
        self.mem_list = ttk.Frame(self.mem_canvas, style="Soft.TFrame")
        self._mem_win = self.mem_canvas.create_window((0, 0), window=self.mem_list, anchor="nw")
        self.mem_list.bind("<Configure>", lambda e: self.mem_canvas.configure(scrollregion=self.mem_canvas.bbox("all")))
        self.mem_canvas.bind("<Configure>", lambda e: self.mem_canvas.itemconfig(self._mem_win, width=e.width))

        # ---------- 勇士表：升级所需局数 / 小时 / 天数 ----------
        war_outer = tk.Frame(left, bg=LINE, padx=1, pady=1)
        war_outer.pack(fill="x", pady=(S2, 0))
        war_box = ttk.Frame(war_outer, style="Soft.TFrame", padding=(S4, S2))
        war_box.pack(fill="x")
        war_head = ttk.Frame(war_box, style="Soft.TFrame")
        war_head.pack(fill="x")
        tk.Frame(war_head, bg=ACCENT, width=3, height=18).pack(side="left", padx=(0, S2))
        ttk.Label(war_head, text="勇士等级计算（1000 起每级 +100）",
                  style="SoftHead.TLabel").pack(side="left")
        self.self_var = tk.IntVar(value=1)
        self.self_chk = tk.Checkbutton(
            war_head,
            text="是否是自己",
            variable=self.self_var,
            command=self._on_self_toggle,
            bg=PANEL,
            fg=TEXT,
            selectcolor=ACCENT_SOFT,
            activebackground=PANEL,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=(FONT_UI, 9),
        )
        self.self_chk.pack(side="right")
        self.war_info = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.war_info.pack(anchor="w", pady=(S2, S2))

        # 四个输入 2×2 排布：比四行更紧凑，结果区能更早进入视野
        grid = ttk.Frame(war_box, style="Soft.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="warcell")
        grid.columnconfigure(1, weight=1, uniform="warcell")
        entries = {}
        for idx, (label, default) in enumerate((
            ("起始等级", ""), ("升至等级", ""),
            ("平均每把积分", "105"), ("一天打多少把", "10"),
        )):
            cell = ttk.Frame(grid, style="Soft.TFrame")
            cell.grid(row=idx // 2, column=idx % 2, sticky="w", pady=S1)
            # 标签固定宽度 + 右对齐：不同字数（起始等级 4 字 / 平均每把积分 6 字）
            # 都占同样宽度，输入框左缘严格对齐，两列竖线成一条直线。
            ttk.Label(
                cell, text=label, style="SoftMuted.TLabel", width=12, anchor="e"
            ).pack(side="left")
            e = ttk.Entry(cell, width=8, justify="center")
            e.pack(side="left", padx=(S2, 0))
            if default:
                e.insert(0, default)
            e.bind("<KeyRelease>", lambda ev: self._render_warrior())
            entries[label] = e
        self.war_start = entries["起始等级"]
        self.war_target = entries["升至等级"]
        self.war_avg = entries["平均每把积分"]
        self.war_games = entries["一天打多少把"]

        tk.Frame(war_box, bg=LINE, height=1).pack(fill="x", pady=(S3, S2))
        self.war_res1 = ttk.Label(war_box, text="—", style="SoftValue.TLabel", wraplength=420)
        self.war_res1.pack(anchor="w", pady=(0, S1))
        self.war_res2 = ttk.Label(war_box, text="—", style="SoftResult.TLabel", wraplength=420)
        self.war_res2.pack(anchor="w", pady=(0, S1))
        self.war_hint = ttk.Label(war_box, text="", style="SoftMuted.TLabel", wraplength=420)
        self.war_hint.pack(anchor="w", pady=(S1, 0))

        # 右侧：近期战绩 / 最佳战绩 两个 tab
        right = ttk.Frame(body, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(S4, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        cols = ("time", "difficulty", "hero", "duration", "bp", "level", "kda", "lh", "gold", "hdmg", "tdmg", "tower")
        headers = (
            ("time", "时间", 148),
            ("difficulty", "难度", 40),
            ("hero", "英雄", 100),
            ("duration", "时长", 52),
            ("bp", "勇士积分", 68),
            ("level", "等级", 34),
            ("kda", "K/D/A", 70),
            ("lh", "补刀", 50),
            ("gold", "金币", 76),
            ("hdmg", "英雄伤害", 80),
            ("tdmg", "承受伤害", 80),
            ("tower", "塔杀", 40),
        )

        self.rec_nb = ttk.Notebook(right, style="TNotebook")
        self.rec_nb.grid(row=0, column=0, sticky="nsew")

        # ---------- 近期战绩 tab ----------
        rec_tab = ttk.Frame(self.rec_nb, style="Dark.TFrame")
        self.rec_nb.add(rec_tab, text="近期战绩")
        rec_tab.rowconfigure(1, weight=1)
        rec_tab.columnconfigure(0, weight=1)

        rec_bar = ttk.Frame(rec_tab, style="Dark.TFrame")
        rec_bar.grid(row=0, column=0, sticky="ew", pady=(0, S2))
        ttk.Label(rec_bar, text="近期战绩", style="Subhead.TLabel").pack(side="left")
        self.lbl_sort_hint = ttk.Label(rec_bar, text="点击可排序", style="Chip.TLabel")
        self.lbl_sort_hint.pack(side="left", padx=(S2, 0))
        # 当前「已选中并生效」的英雄：仅打字时它不变，选中后才高亮
        self.lbl_hero_hint = ttk.Label(rec_bar, text="全部英雄", style="Chip.TLabel")
        self.lbl_hero_hint.pack(side="left", padx=(S2, 0))
        # 英雄筛选两阶段：输入只收窄下拉候选，从下拉选中后才筛表（觉醒/非觉醒同一英雄）
        self.hero_filter_var = tk.StringVar(value="全部英雄")
        ttk.Label(rec_bar, text="英雄", style="Muted.TLabel").pack(side="right", padx=(S2, S2))
        self.hero_filter = ttk.Combobox(
            rec_bar, textvariable=self.hero_filter_var, state="normal", width=16,
            values=("全部英雄",),
        )
        self.hero_filter.pack(side="right")
        self.hero_filter.bind("<<ComboboxSelected>>", self._on_recent_hero_selected)
        self.hero_filter.bind("<KeyRelease>", self._on_recent_hero_typing)
        # 打完字按回车也要能生效；失焦时清掉未确认的半截搜索词
        self.hero_filter.bind("<Return>", self._on_recent_hero_confirm)
        self.hero_filter.bind("<FocusOut>", self._on_recent_hero_blur)

        tree_wrap = tk.Frame(rec_tab, bg=LINE, padx=1, pady=1)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_inner = tk.Frame(tree_wrap, bg=PANEL)
        tree_inner.pack(fill="both", expand=True)
        tree_inner.columnconfigure(0, weight=1)
        tree_inner.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_inner, columns=cols, show="headings", height=30)
        self.tree_headers = {col: text for col, text, _ in headers}
        for col, text, w in headers:
            # 表头点击三态循环：升序 → 降序 → 恢复
            self.tree.heading(col, text=text, command=lambda c=col: self._on_sort(c))
            self.tree.column(col, width=w, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self._style_tree(self.tree)
        vsb = ttk.Scrollbar(
            tree_inner, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar"
        )
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(
            tree_inner, orient="horizontal", command=self.tree.xview, style="Dark.Horizontal.TScrollbar"
        )
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # ---------- 最佳战绩 tab ----------
        best_tab = ttk.Frame(self.rec_nb, style="Dark.TFrame")
        self.rec_nb.add(best_tab, text="最佳战绩")
        best_tab.rowconfigure(1, weight=1)
        best_tab.columnconfigure(0, weight=1)

        best_bar = ttk.Frame(best_tab, style="Dark.TFrame")
        best_bar.grid(row=0, column=0, sticky="ew", pady=(0, S2))
        ttk.Label(best_bar, text="最佳战绩", style="Subhead.TLabel").pack(side="left")
        self.lbl_best_sort_hint = ttk.Label(best_bar, text="点击可排序", style="Chip.TLabel")
        self.lbl_best_sort_hint.pack(side="left", padx=(S2, 0))
        self.lbl_best_hero_hint = ttk.Label(best_bar, text="全部英雄", style="Chip.TLabel")
        self.lbl_best_hero_hint.pack(side="left", padx=(S2, 0))
        # 难度筛选：默认 N8（n6/n7/n8 每个难度各取该英雄用时最短一条）
        ttk.Label(best_bar, text="难度", style="Muted.TLabel").pack(side="right", padx=(S2, S2))
        self.best_diff_var = tk.StringVar(value="N8")
        self.best_diff = ttk.Combobox(
            best_bar, textvariable=self.best_diff_var, state="readonly", width=14,
            values=("N8", "N7", "N6", "全部(N6-N8)"),
        )
        self.best_diff.pack(side="right")
        self.best_diff.bind("<<ComboboxSelected>>", lambda e: self._render_best())
        # 英雄搜索框：与近期战绩同款两阶段筛选，同样按「已选中」的英雄过滤
        self.best_hero_filter_var = tk.StringVar(value="全部英雄")
        ttk.Label(best_bar, text="英雄", style="Muted.TLabel").pack(side="right", padx=(S2, S2))
        self.best_hero_filter = ttk.Combobox(
            best_bar, textvariable=self.best_hero_filter_var, state="normal", width=16,
            values=("全部英雄",),
        )
        self.best_hero_filter.pack(side="right")
        self.best_hero_filter.bind("<<ComboboxSelected>>", self._on_best_hero_selected)
        self.best_hero_filter.bind("<KeyRelease>", self._on_best_hero_typing)
        self.best_hero_filter.bind("<Return>", self._on_best_hero_confirm)
        self.best_hero_filter.bind("<FocusOut>", self._on_best_hero_blur)

        best_wrap = tk.Frame(best_tab, bg=LINE, padx=1, pady=1)
        best_wrap.grid(row=1, column=0, sticky="nsew")
        best_inner = tk.Frame(best_wrap, bg=PANEL)
        best_inner.pack(fill="both", expand=True)
        best_inner.columnconfigure(0, weight=1)
        best_inner.rowconfigure(0, weight=1)
        self.best_tree = ttk.Treeview(best_inner, columns=cols, show="headings", height=30)
        self.best_tree_headers = {col: text for col, text, _ in headers}
        for col, text, w in headers:
            self.best_tree.heading(col, text=text, command=lambda c=col: self._on_best_sort(c))
            self.best_tree.column(col, width=w, anchor="center")
        self.best_tree.grid(row=0, column=0, sticky="nsew")
        self._style_tree(self.best_tree)
        bvsb = ttk.Scrollbar(
            best_inner, orient="vertical", command=self.best_tree.yview, style="Dark.Vertical.TScrollbar"
        )
        bvsb.grid(row=0, column=1, sticky="ns")
        bhsb = ttk.Scrollbar(
            best_inner, orient="horizontal", command=self.best_tree.xview, style="Dark.Horizontal.TScrollbar"
        )
        bhsb.grid(row=1, column=0, sticky="ew")
        self.best_tree.configure(yscrollcommand=bvsb.set, xscrollcommand=bhsb.set)

    def _make_selectable(self, label):
        """让 Label 可被鼠标选中并复制 (Ctrl+C)"""
        label.configure(takefocus=True)
        label.bind("<Button-1>", lambda e: self._start_select(label, e))
        label.bind("<B1-Motion>", lambda e: self._extend_select(label, e))
        label.bind("<ButtonRelease-1>", lambda e: self._end_select(label, e))
        label.bind("<Control-c>", lambda e: self._copy_select(label))

    def _start_select(self, label, event):
        label.focus_set()
        try:
            label.selection_range(0, "end")
            label.selection_anchor(0)
            label.icursor("xterm")
        except Exception:
            pass

    def _extend_select(self, label, event):
        try:
            label.icursor("xterm")
            label.selection_range(0, f"@{event.x}")
        except Exception:
            pass

    def _end_select(self, label, event):
        try:
            label.selection_clear()
        except Exception:
            pass

    def _copy_select(self, label):
        try:
            text = label.selection_get()
        except Exception:
            text = label.cget("text")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.lbl_status.config(text=f"已复制: {text}")

    # ================= 会员表 / 勇士表 =================
    def _on_mousewheel(self, event):
        """左列和会员表各自滚动；鼠标在右侧战绩表时不干预"""
        path = str(event.widget)
        step = -3 if event.delta > 0 else 3
        if path == str(self.mem_canvas) or path.startswith(str(self.mem_canvas) + "."):
            self.mem_canvas.yview_scroll(step, "units")
        elif path == str(self.day_canvas) or path.startswith(str(self.day_canvas) + "."):
            self.day_canvas.yview_scroll(step, "units")
        elif path == str(self.month_canvas) or path.startswith(str(self.month_canvas) + "."):
            self.month_canvas.yview_scroll(step, "units")
        elif path == str(self.left_canvas) or path.startswith(str(self.left_canvas) + "."):
            self.left_canvas.yview_scroll(step, "units")
