"""App Mixin：概览卡、会员/勇士表、每日/每月统计与战绩表渲染、排序过滤。"""

import math
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from .domain import MEMBER_BASE, MEMBER_STEP, SORT_KEYS, WARRIOR_BASE, WARRIOR_STEP, fmt_duration, level_cum, level_from_exp
from .theme import ACCENT, BG, BTN_HOVER, DANGER, FONT_NUM, FONT_UI, LINE, MUTED, PANEL, PANEL_SOFT, S2, TEXT


class UIRenderMixin:

    def _toggle_member(self):
        self.member_open = not self.member_open
        if self.member_open:
            self.mem_body.pack(fill="x", pady=(S2, 0), after=self.mem_summary)
            self.mem_toggle.config(text="会员等级预测（未来 100 级）  ▲")
        else:
            self.mem_body.pack_forget()
            self.mem_toggle.config(text="会员等级预测（未来 100 级）  ▼")
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    @staticmethod
    def _num(widget, default=None):
        try:
            return float(widget.get().strip())
        except (ValueError, AttributeError, tk.TclError):
            return default

    def _render_member_table(self):
        """按每天固定会员经验，推算未来 100 级的达成日期与所需天数；竖向排列，三列带表头"""
        signature = (
            self.profile.get("memberPointTotal"),
            self._num(self.mem_daily),
            datetime.now().date(),
        )
        if signature == self._mem_signature:
            return  # 自动刷新数据没变就不重建，避免闪烁与滚动跳动
        self._mem_signature = signature
        view = self.mem_canvas.yview()
        for c in self.mem_list.winfo_children():
            c.destroy()
        total = self.profile.get("memberPointTotal") or 0
        cur = level_from_exp(total, MEMBER_STEP, MEMBER_BASE)
        daily = self._num(self.mem_daily)
        if not total or daily is None or daily <= 0:
            self.mem_summary.config(text="当前会员经验未知，或「每日经验」需填写大于 0 的数字")
            return

        today = datetime.now().date()
        items = []  # (lv, date, days)
        for i in range(1, 101):
            lv = cur + i
            need = level_cum(lv, MEMBER_STEP, MEMBER_BASE) - total
            days = max(0, math.ceil(need / daily))
            items.append((lv, (today + timedelta(days=days)).strftime("%Y-%m-%d"), days))

        for idx, (lv, d, days) in enumerate(items):
            bg = PANEL if idx % 2 == 0 else PANEL_SOFT
            row = tk.Frame(self.mem_list, bg=bg)
            row.pack(fill="x")
            vals = (f"{lv} 级", d, f"{days} 天")
            for i, ((_text, w), val) in enumerate(zip(self.mem_cols_def, vals)):
                row.columnconfigure(i, minsize=w, weight=1)
                # 等级列用强调色突出，达成日期常规字，所需天数弱化
                fg = ACCENT if i == 0 else (TEXT if i == 1 else MUTED)
                lbl = tk.Label(
                    row, text=val, bg=bg, fg=fg,
                    font=(FONT_NUM, 12), anchor="center", pady=4,
                )
                lbl.grid(row=0, column=i, sticky="ew")
                self._make_selectable(lbl)
            tk.Frame(self.mem_list, bg=LINE, height=1).pack(fill="x")

        self.mem_canvas.yview_moveto(view[0])
        self.mem_summary.config(
            text=(
                f"当前 {cur} 级 · 总经验 {total:,} · 本级 "
                f"{self.profile.get('memberCurrPoint', 0):,}/{self.profile.get('memberNextPoint', 0):,}"
                f" · 按每天 {daily:g} 经验\n"
                f"{cur + 1}~{cur + 100} 级（最近一级 {items[0][1]} · 约 {items[0][2]} 天；仅计每日签到，可在上方修改）"
            )
        )
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _on_self_toggle(self, keep_manual=False):
        """勾选「是自己」→ 起始等级置灰并用自己当前总积分起算；取消 → 置空可填。
        升到等级默认 = 起始等级 +10，方便直接看到预测结果。"""
        own = level_from_exp(self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE)
        self.war_start.configure(state="normal")
        if self.self_var.get():
            self.war_start.delete(0, "end")
            self.war_start.insert(0, str(own))
            self.war_start.configure(state="disabled")
            # 升到等级仅在用户尚未填写时给默认（起始+10），
            # 避免自动刷新每轮覆盖用户已改的值
            if not self.war_target.get().strip():
                self.war_target.delete(0, "end")
                self.war_target.insert(0, str(own + 10))
        elif not keep_manual:
            # 显式取消勾选：清空两个等级框，由用户手动填写
            self.war_start.delete(0, "end")
            self.war_target.delete(0, "end")
        elif not self.war_target.get().strip():
            # 未勾选但保留手动值：升到等级为空时按「起始等级 +10」给默认
            start = self._num(self.war_start)
            if start is not None:
                self.war_target.delete(0, "end")
                self.war_target.insert(0, str(int(start) + 10))
        self._render_warrior()

    def _render_warrior(self):
        p = self.profile
        total = p.get("seasonPointTotal") or 0
        own = level_from_exp(total, WARRIOR_STEP, WARRIOR_BASE)
        self.war_info.config(
            text=(
                f"自己勇士：{own} 级 · 总积分 {total:,} · 本级 "
                f"{p.get('seasonCurrPoint', 0):,}/{p.get('seasonNextPoint', 0):,}"
                f" · 近期场均 {fmt_duration(self.avg_duration)}"
            )
        )

        if self.self_var.get():
            start_level, start_exp = own, total
        else:
            start_level = self._num(self.war_start)
            start_exp = level_cum(int(start_level), WARRIOR_STEP, WARRIOR_BASE) if start_level else None
        target = self._num(self.war_target)
        avg = self._num(self.war_avg)
        gpd = self._num(self.war_games)

        if start_exp is None or target is None or avg is None or gpd is None or avg <= 0 or gpd <= 0:
            self.war_res1.config(text="请填写有效的起始等级 / 升至等级 / 积分 / 每天把数")
            self.war_res2.config(text="")
            self.war_hint.config(text="")
            return

        target = int(target)
        need = level_cum(target, WARRIOR_STEP, WARRIOR_BASE) - start_exp
        if need <= 0:
            self.war_res1.config(text=f"升至等级需高于起始等级（当前按 {start_level:g} 级起算）")
            self.war_res2.config(text="")
            self.war_hint.config(text="")
            return

        games_pure = math.ceil(need / avg)
        hours_pure = games_pure * self.avg_duration / 3600 if self.avg_duration else 0
        daily_pts = gpd * avg + self.task_points
        days = math.ceil(need / daily_pts)
        games_real = max(0, math.ceil((need - days * self.task_points) / avg))
        hours_real = games_real * self.avg_duration / 3600 if self.avg_duration else 0

        self.war_res1.config(
            text=(
                f"需要 {games_pure:,} 局 · 约 {hours_pure:,.1f} 小时"
                f"（纯靠对局，场均 {fmt_duration(self.avg_duration)}）"
            )
        )
        self.war_res2.config(
            text=(
                f"需要 {days:,} 天 · 约 {days / 30.4:.1f} 个月"
                f"（每天 {gpd:g} 把 × {avg:g} + 任务 {self.task_points} = {daily_pts:,.0f} 积分）"
            )
        )
        self.war_hint.config(
            text=(
                f"{start_level:g} 级 → {target} 级 共需 {need:,} 积分；"
                f"计入每天 {self.task_points} 任务奖励后，实际约 {games_real:,} 局 / {hours_real:,.1f} 小时"
                f"（「是自己」时按当前总积分 {total:,} 起算）"
            )
        )

    def _style_tree(self, tree, big=False):
        """配置表格样式。big=True 使用更大字体"""
        style = ttk.Style()
        name = "BigTreeview" if big else "Treeview"
        head = "BigTreeview.Heading" if big else "Treeview.Heading"
        font = (FONT_UI, 11) if big else (FONT_UI, 10)
        rowh = 34 if big else 28

        style.configure(
            name,
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=rowh,
            borderwidth=0,
            relief="flat",
            font=font,
        )
        style.configure(
            head,
            background=PANEL_SOFT,
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            padding=(4, 6),
            font=(FONT_UI, 9, "bold"),
        )
        # 表头悬停用深色高亮 + 强调色文字；选中行蓝底配深色字，避免
        # clam 默认的白字蓝底（#ffffff / #4a6984）对比不足。
        style.map(head, background=[("active", BTN_HOVER)],
                  foreground=[("active", ACCENT)])
        style.map(name, background=[("selected", ACCENT)],
                  foreground=[("selected", BG)])
        if tree is not None:
            tree.tag_configure("odd", background=PANEL, foreground=TEXT)
            tree.tag_configure("even", background=PANEL_SOFT, foreground=TEXT)

    # ---------- 区块渲染：每日统计（仅近期战绩接口成功才重建） ----------
    def _render_stats_rows(self, frame, cols_def, rows, canvas):
        """每日 / 每月统计共用：斑马纹 + 1px 细线，固定 10 行高度内滚动。"""
        for c in frame.winfo_children():
            c.destroy()
        for idx, d in enumerate(rows):
            eff = f"{d['eff']:.2f}" if d["eff"] >= 0 else "-"
            cells = (d["date"], d["count"], f"{d['points']:,}", d["time"], eff)
            bg = PANEL if idx % 2 == 0 else PANEL_SOFT
            row = tk.Frame(frame, bg=bg)
            row.pack(fill="x")
            for i, ((text, w), val) in enumerate(zip(cols_def, cells)):
                row.columnconfigure(i, minsize=w)
                if text == "效率":
                    fg = DANGER if d["eff"] < 0 else ACCENT  # 只用一种强调色标出关键指标
                else:
                    fg = MUTED if i == 0 else TEXT
                lbl = tk.Label(
                    row, text=str(val), bg=bg, fg=fg,
                    font=(FONT_NUM, 14), anchor="center", pady=6,
                )
                lbl.grid(row=0, column=i, sticky="ew")
                self._make_selectable(lbl)
            tk.Frame(frame, bg=LINE, height=1).pack(fill="x")
        frame.update_idletasks()
        self._sync_stats_scrollregion(canvas)

    def _sync_stats_scrollregion(self, canvas):
        """统计表滚动区域至少覆盖可视高度，杜绝内容不足一屏时滚出空白。

        canvas 固定 10 行可视高度，但 bbox("all") 只到内容实际高度（如 2 行
        仅 72px）。若直接把它当 scrollregion，Tk 会把可滚动范围扩展到一屏，
        多出来的部分全是空白；用户往上拉滚动条就会看到数据贴底、上方空白。
        内容不足一屏时把 scrollregion 撑满可视高度并复位到顶部；内容超过
        一屏则保留正常滚动，且重建后不打断用户当前的阅读位置。
        """
        bbox = canvas.bbox("all")
        if not bbox:
            return
        x0, y0, x1, y1 = bbox
        # canvas 用 pack(fill="x") 不压缩高度，配置高度即真实可视高度；
        # 用配置值而非 winfo_height() 可避开窗口未映射时的 1px 失真。
        visible_h = int(float(canvas.cget("height")))
        canvas.configure(scrollregion=(x0, y0, x1, max(y1, y0 + visible_h)))
        if (y1 - y0) <= visible_h:
            canvas.yview_moveto(0)

    # ---------- 区块渲染：每日 / 每月统计（含表头筛选 + 表头排序） ----------
    # 表头列名 → 行字典排序键；日期/月份已是 YYYY-MM-DD / YYYY-MM 文本，字典序即时间序；
    # 总耗时用数值 sec（秒），避免按 "2时3分" 这样的展示串字典序排序出错
    _STATS_SORT_KEYS = {
        "日期": "date", "月份": "date",
        "场次": "count", "积分": "points", "总耗时": "sec", "效率": "eff",
    }

    def _apply_stats_sort(self, kind, rows):
        """按当前排序状态排序；state=0 或不排则返回原顺序（保持库的 DESC 自然序）。"""
        col = self.day_sort_col if kind == "day" else self.month_sort_col
        state = self.day_sort_state if kind == "day" else self.month_sort_state
        if not col or not state:
            return rows
        key = self._STATS_SORT_KEYS.get(col)
        if key is None:
            return rows
        return sorted(rows, key=lambda d: d[key], reverse=(state == 2))

    def _on_stats_sort(self, kind, col):
        """每日/每月统计表头三态循环：升序 → 降序 → 恢复原始顺序；换列从升序开始。"""
        if getattr(self, "_closed", False):
            return
        col_attr = f"{kind}_sort_col"
        state_attr = f"{kind}_sort_state"
        cur_col = getattr(self, col_attr)
        cur_state = getattr(self, state_attr)
        if cur_col == col:
            cur_state = (cur_state + 1) % 3
        else:
            cur_col, cur_state = col, 1
        if cur_state == 0:
            cur_col = None
        setattr(self, col_attr, cur_col)
        setattr(self, state_attr, cur_state)
        self._update_stats_headings(kind)
        if kind == "day":
            self._render_days()
        else:
            self._render_months()

    def _update_stats_headings(self, kind):
        """每日/每月统计表头排序标记 + 提示条（与近期战绩同款三态）。"""
        labels = getattr(self, f"{kind}_head_labels", {})
        col = getattr(self, f"{kind}_sort_col")
        state = getattr(self, f"{kind}_sort_state")
        for name, lbl in labels.items():
            mark = ""
            if name == col and state:
                mark = " ▲" if state == 1 else " ▼"
            try:
                lbl.config(text=name + mark)
            except tk.TclError:
                pass
        hint = getattr(self, f"{kind}_sort_hint", None)
        if hint is not None:
            if col and state:
                arrow = "▲" if state == 1 else "▼"
                hint.configure(text=f"排序：{col} {arrow}", style="SortActive.TLabel")
            else:
                hint.configure(text="点击可排序", style="Chip.TLabel")

    def _filtered_days(self):
        f = getattr(self, "_day_filter", "全部")
        if not f or f == "全部":
            return self.days
        return [d for d in self.days if d["date"].startswith(f)]

    def _filtered_months(self):
        f = getattr(self, "_month_filter", "全部")
        if not f or f == "全部":
            return self.months
        return [m for m in self.months if m["date"].startswith(f)]

    def _update_stats_filter_candidates(self, kind, prefixes):
        """刷新筛选下拉候选：每日取年月、每月取年，去重排序后回填（不动当前输入）。"""
        cands = sorted(set(prefixes))
        setattr(self, f"_{kind}_filter_cands", cands)
        combo = getattr(self, f"{kind}_filter_combo", None)
        if combo is None:
            return
        cur = combo.get().strip() or "全部"
        if not cur or cur == "全部":
            combo["values"] = ["全部"] + cands
        else:
            combo["values"] = ["全部"] + [c for c in cands if c.startswith(cur)]

    def _render_days(self):
        self._update_stats_filter_candidates("day", [d["date"][:7] for d in self.days])
        rows = self._apply_stats_sort("day", self._filtered_days())
        self._render_stats_rows(
            self.day_rows_frame, self.day_cols_def, rows, self.day_canvas
        )
        self._update_stats_headings("day")

    def _render_months(self):
        self._update_stats_filter_candidates("month", [m["date"][:4] for m in self.months])
        rows = self._apply_stats_sort("month", self._filtered_months())
        self._render_stats_rows(
            self.month_rows_frame, self.month_cols_def, rows, self.month_canvas
        )
        self._update_stats_headings("month")

    def _on_stats_filter_changed(self, kind):
        """从下拉点选或回车确认后应用筛选：更新生效值并重渲染对应统计表。"""
        if getattr(self, "_closed", False):
            return
        combo = getattr(self, f"{kind}_filter_combo", None)
        text = combo.get().strip() if combo is not None else "全部"
        text = text or "全部"
        setattr(self, f"_{kind}_filter", text)
        if kind == "day":
            self._render_days()
        else:
            self._render_months()

    def _on_stats_filter_typing(self, kind):
        """打字阶段即时应用前缀筛选，并按输入收窄候选下拉（不抢输入、不影响表格滚动）。"""
        self._on_stats_filter_changed(kind)
        combo = getattr(self, f"{kind}_filter_combo", None)
        if combo is None:
            return
        text = combo.get().strip()
        all_cands = getattr(self, f"_{kind}_filter_cands", [])
        if not text or text == "全部":
            combo["values"] = ["全部"] + all_cands
        else:
            combo["values"] = ["全部"] + [c for c in all_cands if c.startswith(text)]

    # ---------- 区块渲染：概览卡片（排行榜/赛季/会员/总场次） ----------
    def _render_cards(self):
        p = self.profile
        sig = (
            p.get("rank"), p.get("seasonLevel"), p.get("seasonNeed"),
            p.get("memberLevel"), p.get("memberNeed"),
            p.get("matchCount"), p.get("winCount"),
        )
        if sig == self._card_signature:
            return  # 数据未变不重绘卡片，避免每轮闪烁
        self._card_signature = sig
        # 4 张卡骨架在 _build_ui 已固定建好，这里只原地更新文字，
        # 副文本行高度始终预留，加载前后高度不变（R040）。
        # 空副文本用空格占位（ttk.Label 空 text 会塌缩到 1px，空格保留整行高度）。
        EMPTY = " "
        s = self._card_slots

        # 0 排行榜排名
        s[0]["value"].config(text=f"{p.get('rank', '-')} 名")
        s[0]["sub_l"].config(text=EMPTY)
        s[0]["sub_r"].config(text=EMPTY)

        # 1 赛季等级
        if p.get("seasonLevel") is not None:
            s[1]["value"].config(text=f"{p['seasonLevel']} 级")
            need = p.get("seasonNeed")
            if need is not None:
                s[1]["sub_l"].config(text=f"距 {p['seasonLevel'] + 1} 级还差 ")
                s[1]["sub_r"].config(text=f"{need:,}")
            else:
                s[1]["sub_l"].config(text=EMPTY)
                s[1]["sub_r"].config(text=EMPTY)
        else:
            s[1]["value"].config(text="— 级")
            s[1]["sub_l"].config(text=EMPTY)
            s[1]["sub_r"].config(text=EMPTY)

        # 2 会员等级
        if p.get("memberLevel") is not None:
            s[2]["value"].config(text=f"{p['memberLevel']} 级")
            need = p.get("memberNeed")
            if need is not None:
                s[2]["sub_l"].config(text=f"距 {p['memberLevel'] + 1} 级还差 ")
                s[2]["sub_r"].config(text=f"{need:,}")
            else:
                s[2]["sub_l"].config(text=EMPTY)
                s[2]["sub_r"].config(text=EMPTY)
        else:
            s[2]["value"].config(text="— 级")
            s[2]["sub_l"].config(text=EMPTY)
            s[2]["sub_r"].config(text=EMPTY)

        # 3 总场次
        if p.get("matchCount"):
            s[3]["value"].config(text=f"{p['matchCount']:,}")
            if p.get("winCount") is not None:
                s[3]["sub_l"].config(text=f"胜率 {p['winCount'] / p['matchCount'] * 100:.1f}%")
            else:
                s[3]["sub_l"].config(text=EMPTY)
            s[3]["sub_r"].config(text=EMPTY)
        else:
            s[3]["value"].config(text="—")
            s[3]["sub_l"].config(text=EMPTY)
            s[3]["sub_r"].config(text=EMPTY)

    def render(self, data):
        """整页渲染入口（测试 / 兜底 / 手动全量刷新用）。

        内部逐接口复用 _on_data_* / _apply_recent_data 的独立比对+更新逻辑，
        与并行刷新路径行为一致：某接口失败则保留上一轮已成功的该区块内容。
        """
        self.lbl_updated.config(text=f"更新于 {data['updatedAt']}")
        # 接口失败保持静默：不写入状态栏、状态灯不转红；失败接口按 failed 集合
        # 跳过对应区块，保留上一轮已成功的旧内容（详见 R034）。

        # 逐接口独立比对、独立更新：失败接口跳过该区块，保留上一轮已成功内容
        failed = set(data.get("failed", []))
        p = data["profile"]
        if "排行榜" not in failed:
            self._on_data_ranking(p)
        if "会员/赛季资料" not in failed:
            self._on_data_info(p)
        if "近期战绩" not in failed:
            self._apply_recent_data(
                data["rows"], data["days"], data.get("avgDurationSec") or 0
            )

        # 勇士目标等级仅在为空时自动预填一次（依赖会员/赛季经验）
        if not self.war_target.get().strip():
            self.war_target.insert(
                0,
                str(level_from_exp(
                    self.profile.get("seasonPointTotal") or 0, WARRIOR_STEP, WARRIOR_BASE) + 10),
            )
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _update_headings(self):
        """表头排序标记：当前排序列显示方向箭头 ▲/▼（醒目且随点击切换），
        并在表头提示条同步高亮当前排序；未排序时提示可点击排序。"""
        for col, text in self.tree_headers.items():
            mark = ""
            if col == self.sort_col and self.sort_state:
                mark = " ▲" if self.sort_state == 1 else " ▼"
            self.tree.heading(col, text=text + mark)
        # 表头提示条：随排序状态变化，醒目高亮当前排序；未排序时仅作可点击提示
        if self.sort_col and self.sort_state:
            arrow = "▲" if self.sort_state == 1 else "▼"
            self.lbl_sort_hint.configure(
                text=f"排序：{self.tree_headers[self.sort_col]} {arrow}",
                style="SortActive.TLabel",
            )
        else:
            self.lbl_sort_hint.configure(text="点击可排序", style="Chip.TLabel")

    def _on_sort(self, col):
        """点击表头三态循环：升序 → 降序 → 恢复原始顺序；换列从升序开始。"""
        if self.sort_col == col:
            self.sort_state = (self.sort_state + 1) % 3
        else:
            self.sort_col, self.sort_state = col, 1
        if self.sort_state == 0:
            self.sort_col = None
        self._update_headings()
        self.apply_filter()

    # ================= 通用表格填充（近期 / 最佳 共用） =================
    @staticmethod
    def _row_display_values(r):
        """把一行战绩展开为 12 列展示值；觉醒 / 掉线以后缀标注（英雄名本身不含觉醒）。"""
        hero = r["hero"] + ("  [觉醒]" if r["awaken"] else "") + ("  [掉线]" if r["disconnected"] else "")
        return (
            r["time"], r["difficulty"], hero, r["durationText"],
            f"+{r['battlePoints']}", r["level"],
            f"{r['kills']}/{r['deaths']}/{r['assists']}",
            f"{r['lastHits']:,}", f"{r['gold']:,}",
            f"{r['heroDamage']:,}", f"{r['damageTaken']:,}", r["towerKills"],
        )

    def _fill_tree(self, tree, rows, sort_col, sort_state):
        """清空并按排序键（若有）重排后填充；重建后恢复滚动位置，刷新 / 排序不弹回顶部。"""
        if sort_col and sort_state:
            rows = sorted(rows, key=SORT_KEYS[sort_col], reverse=sort_state == 2)
        view = tree.yview()
        tree.delete(*tree.get_children())
        for i, r in enumerate(rows):
            tree.insert(
                "", "end", values=self._row_display_values(r),
                tags=("even" if i % 2 else "odd",),
            )
        if view and view != (0.0, 1.0) and tree.get_children():
            tree.yview_moveto(view[0])

    # ================= 英雄两阶段筛选（近期 / 最佳 共用） =================
    # 语义：输入框里的文本只是「搜索下拉候选用的关键字」，真正生效的筛选值
    # 只来自用户从下拉里选中的那一项，存在 self.hero_selected["recent"/"best"]。
    # 因此打字阶段不动表格，排序 / 难度切换 / 自动刷新也不会被半输入的词误筛。
    ALL_HEROES = "全部英雄"

    def _hero_options(self, typed):
        """按输入文本收窄下拉候选；首项恒为「全部英雄」以便随时清除筛选。"""
        q = (typed or "").strip().lower()
        if q and q != self.ALL_HEROES.lower():
            return [self.ALL_HEROES] + [h for h in self.heroes_list if q in h.lower()]
        return [self.ALL_HEROES] + list(self.heroes_list)

    def _hero_pairs(self):
        """两个 tab 的 (key, var, combobox, 提示标签, 重渲染回调)。"""
        return (
            ("recent", self.hero_filter_var, self.hero_filter,
             self.lbl_hero_hint, self.apply_filter),
            ("best", self.best_hero_filter_var, self.best_hero_filter,
             self.lbl_best_hero_hint, self._render_best),
        )

    def _update_hero_hint(self, key, hint):
        """提示条显示当前真正生效的英雄；仅打字阶段保持不变。"""
        sel = self.hero_selected.get(key, self.ALL_HEROES)
        if sel == self.ALL_HEROES:
            hint.configure(text="全部英雄", style="Chip.TLabel")
        else:
            hint.configure(text=f"筛选：{sel}", style="SortActive.TLabel")

    def _hero_combo(self, key):
        return self.hero_filter if key == "recent" else self.best_hero_filter

    def _hero_set_text(self, combo, var, value):
        """程序内部写输入框：抑制 trace，避免被误判为用户输入而收窄候选/弹下拉。"""
        guard = getattr(self, "_hero_trace_guard", False)
        self._hero_trace_guard = True
        try:
            combo.set(value)
            var.set(value)
        finally:
            self._hero_trace_guard = guard

    def _on_hero_var_changed(self, key, *_):
        """文本变化 → 收窄候选。中文输入法合成结束不派发 <KeyRelease>，
        只有 textvariable 的 write trace 能可靠捕获；粘贴 / 键盘同样覆盖。
        只改候选，绝不碰生效值与表格。
        """
        if getattr(self, "_hero_trace_guard", False):
            return
        combo = self._hero_combo(key)
        try:
            combo["values"] = self._hero_options(self._hero_var(key).get())
        except tk.TclError:
            return
        self._schedule_hero_popdown(key, combo)

    def _on_recent_hero_var_changed(self, *_):
        self._on_hero_var_changed("recent")

    def _on_best_hero_var_changed(self, *_):
        self._on_hero_var_changed("best")

    def _post_hero_popdown(self, combo):
        """展开下拉但绝不改编辑框文本：ttk 的 <Down> 会用候选项覆盖文本，
        中文输入法刚提交的字正是这样被冲成「全部英雄」的。
        """
        try:
            if combo.winfo_ismapped() and not getattr(self, "_closed", False):
                combo.tk.call("ttk::combobox::Post", str(combo))
        except tk.TclError:
            pass

    def _schedule_hero_popdown(self, key, combo):
        """输入停止 450ms 且文本是英雄名/前缀才展开下拉：不抢在中文输入法
        拼音组字的候选窗口前面，也把连续打字的多次 trace 合并成一次。
        """
        jobs = self._hero_popdown_jobs
        old = jobs.get(key)
        if old:
            try:
                combo.after_cancel(old)
            except tk.TclError:
                pass

        def post():
            jobs[key] = None
            try:
                text = combo.get().strip()
            except tk.TclError:
                return
            if not text or text == self.ALL_HEROES:
                return
            if not any(text.lower() in h.lower() for h in self.heroes_list):
                return
            self._post_hero_popdown(combo)

        try:
            jobs[key] = combo.after(450, post)
        except tk.TclError:
            jobs[key] = None

    def _refresh_hero_options(self):
        """数据变化时刷新全量英雄、同步两个下拉候选。
        已选英雄消失则回落「全部英雄」；仍在输入的中文前缀保留，不把字冲掉。
        """
        self.heroes_list = sorted({r["hero"] for r in self.rows})
        full = [self.ALL_HEROES] + list(self.heroes_list)
        for key, var, combo, hint, _ in self._hero_pairs():
            sel = self.hero_selected.get(key, self.ALL_HEROES)
            if sel != self.ALL_HEROES and sel not in self.heroes_list:
                sel = self.ALL_HEROES
                self.hero_selected[key] = sel
            cur = combo.get().strip()
            keeps_typing = bool(cur) and cur != sel and any(
                cur.lower() in h.lower() for h in self.heroes_list
            )
            if keeps_typing:
                combo["values"] = self._hero_options(cur)
            else:
                self._hero_set_text(combo, var, sel)
                combo["values"] = full
            self._update_hero_hint(key, hint)

    def _on_hero_typing(self, combo, event=None):
        """按键兜底：只同步候选；展开下拉由 trace 统一延迟调度。

        绝不再 event_generate("<Down>")：ttk 的 Down 会用候选项覆盖编辑框文本。
        """
        try:
            combo["values"] = self._hero_options(combo.get())
        except tk.TclError:
            pass

    def _on_recent_hero_typing(self, event=None):
        self._on_hero_typing(self.hero_filter, event)

    def _on_best_hero_typing(self, event=None):
        self._on_hero_typing(self.best_hero_filter, event)

    def _on_hero_selected(self, key, var, combo, hint, rerender, event=None):
        """从下拉点选 → 该英雄成为生效筛选：还原完整候选、更新提示、重渲染。"""
        chosen = combo.get().strip() or self.ALL_HEROES
        self._hero_set_text(combo, var, chosen)
        self.hero_selected[key] = chosen
        # 选中即收起延迟展开任务，别在 300ms 后又把下拉弹出来
        job = self._hero_popdown_jobs.get(key)
        if job:
            try:
                combo.after_cancel(job)
            except tk.TclError:
                pass
            self._hero_popdown_jobs[key] = None
        combo["values"] = [self.ALL_HEROES] + list(self.heroes_list)
        self._update_hero_hint(key, hint)
        rerender()

    def _on_recent_hero_selected(self, event=None):
        self._on_hero_selected("recent", self.hero_filter_var, self.hero_filter,
                               self.lbl_hero_hint, self.apply_filter, event)

    def _on_best_hero_selected(self, event=None):
        self._on_hero_selected("best", self.best_hero_filter_var, self.best_hero_filter,
                               self.lbl_best_hero_hint, self._render_best, event)

    def _hero_confirm(self, key, combo, hint, rerender, event=None):
        """回车确认：把输入解析成「已选中」的英雄，是两阶段的第二条生效路径。

        优先级：空 / 全部英雄 → 清除筛选；精确匹配 → 该英雄；唯一子串匹配 →
        自动补全并生效；多个匹配 → 不改表、保留下拉等用户点选；无匹配 → 复位
        成上一次已生效值。这样打「影」回车即可选中唯一的「影魔」。
        """
        typed = combo.get().strip()
        if not typed or typed == self.ALL_HEROES:
            chosen = self.ALL_HEROES
        elif typed in self.heroes_list:
            chosen = typed
        else:
            q = typed.lower()
            matches = [h for h in self.heroes_list if q in h.lower()]
            if len(matches) == 1:
                chosen = matches[0]
            elif matches:
                return  # 多个候选：交给下拉点选，不擅自选错英雄
            else:
                return  # 无匹配：保留用户输入的文字，绝不改写输入框
        self._hero_set_text(combo, self._hero_var(key), chosen)
        self._on_hero_selected(key, self._hero_var(key), combo, hint, rerender, event)

    def _hero_var(self, key):
        return self.hero_filter_var if key == "recent" else self.best_hero_filter_var

    def _on_recent_hero_confirm(self, event=None):
        self._hero_confirm("recent", self.hero_filter, self.lbl_hero_hint,
                           self.apply_filter, event)

    def _on_best_hero_confirm(self, event=None):
        self._hero_confirm("best", self.best_hero_filter, self.lbl_best_hero_hint,
                           self._render_best, event)

    # <Return> 走延迟确认：中文输入法常用回车把候选词上屏，按键瞬间编辑框里
    # 还是空的，立即解析会把「上屏」误判成「清空」，把框写回「全部英雄」。
    def _on_hero_return(self, key, combo, hint, rerender, event=None):
        try:
            before = combo.get()
        except tk.TclError:
            return
        try:
            combo.after(120, lambda: self._hero_return_deferred(
                key, combo, hint, rerender, before))
        except tk.TclError:
            self._hero_return_deferred(key, combo, hint, rerender, before)

    def _hero_return_deferred(self, key, combo, hint, rerender, before):
        """延迟回调：文本在回车之后才变化（IME 上屏）或为空时一律不确认。"""
        if getattr(self, "_closed", False):
            return
        try:
            after = combo.get()
        except tk.TclError:
            return
        if not after.strip() or after != before:
            return  # 不动输入框、不动筛选，候选已由 trace 收窄
        self._hero_confirm(key, combo, hint, rerender)

    def _on_recent_hero_return(self, event=None):
        self._on_hero_return("recent", self.hero_filter, self.lbl_hero_hint,
                             self.apply_filter, event)

    def _on_best_hero_return(self, event=None):
        self._on_hero_return("best", self.best_hero_filter, self.lbl_best_hero_hint,
                             self._render_best, event)

    def _hero_blur(self, key, combo, event=None):
        """失焦：延迟复位，避免抢在 <<ComboboxSelected>> 之前把刚点中的值清掉。"""
        try:
            combo.after(150, lambda k=key, c=combo: self._hero_blur_deferred(k, c))
        except tk.TclError:
            self._hero_blur_deferred(key, combo)

    def _hero_blur_deferred(self, key, combo):
        """失焦后清掉未完成选中的半截搜索词，恢复成已生效值。"""
        if getattr(self, "_closed", False):
            return
        try:
            cur = combo.get().strip()
        except tk.TclError:
            return
        sel = self.hero_selected.get(key, self.ALL_HEROES)
        if cur == sel:
            return
        # 中文输入法打到一半的前缀（「兽」是「兽王」的子串）保留，别冲掉刚打的字
        if any(cur.lower() in h.lower() for h in self.heroes_list):
            return
        self._hero_set_text(combo, self._hero_var(key), sel)
        combo["values"] = [self.ALL_HEROES] + list(self.heroes_list)

    def _on_recent_hero_blur(self, event=None):
        self._hero_blur("recent", self.hero_filter, event)

    def _on_best_hero_blur(self, event=None):
        self._hero_blur("best", self.best_hero_filter, event)

    def apply_filter(self):
        """近期战绩：按「已选中」的英雄筛选（觉醒 / 非觉醒视为同一英雄）+ 三态排序。"""
        q = self.hero_selected.get("recent", self.ALL_HEROES)
        if q and q != self.ALL_HEROES:
            ql = q.lower()
            rows = [r for r in self.rows if ql in r["hero"].lower()]
        else:
            rows = list(self.rows)
        self._fill_tree(self.tree, rows, self.sort_col, self.sort_state)
        self._update_headings()

    # ================= 最佳战绩：每英雄 × 每难度取用时最短一条 =================
    def _render_best(self):
        """全量数据（self.rows）里，每个英雄在 n6/n7/n8 各取用时最短（durationSec 最小）的一条。

        难度筛选（默认 N8）决定展示哪一难度；「全部(N6-N8)」则每个英雄列三行。
        觉醒 / 非觉醒是同一英雄（hero 字段已不含觉醒），按 hero 聚合即可。
        """
        diff = self.best_diff_var.get()
        allowed = {"N6", "N7", "N8"} if diff == "全部(N6-N8)" else {diff}
        # 与近期战绩同款两阶段筛选：只认「已选中」的英雄，忽略正在输入的搜索词
        hero = self.hero_selected.get("best", self.ALL_HEROES)
        hero_q = hero.lower() if hero != self.ALL_HEROES else ""
        best = {}
        for r in self.rows:
            d = r["difficulty"]
            if d not in allowed:
                continue
            if hero_q and hero_q not in r["hero"].lower():
                continue
            key = (r["hero"], d)
            cur = best.get(key)
            if cur is None or r["durationSec"] < cur["durationSec"]:
                best[key] = r
        rows = sorted(best.values(), key=lambda r: (r["hero"], r["difficulty"]))
        self._fill_tree(self.best_tree, rows, self.best_sort_col, self.best_sort_state)
        self._update_best_headings()

    def _update_best_headings(self):
        """最佳战绩表头排序标记 + 提示条同步（与近期战绩同款三态逻辑）。"""
        for col, text in self.best_tree_headers.items():
            mark = ""
            if col == self.best_sort_col and self.best_sort_state:
                mark = " ▲" if self.best_sort_state == 1 else " ▼"
            self.best_tree.heading(col, text=text + mark)
        if self.best_sort_col and self.best_sort_state:
            arrow = "▲" if self.best_sort_state == 1 else "▼"
            self.lbl_best_sort_hint.configure(
                text=f"排序：{self.best_tree_headers[self.best_sort_col]} {arrow}",
                style="SortActive.TLabel",
            )
        else:
            self.lbl_best_sort_hint.configure(text="点击可排序", style="Chip.TLabel")

    def _on_best_sort(self, col):
        """最佳战绩表头三态循环排序。"""
        if self.best_sort_col == col:
            self.best_sort_state = (self.best_sort_state + 1) % 3
        else:
            self.best_sort_col, self.best_sort_state = col, 1
        if self.best_sort_state == 0:
            self.best_sort_col = None
        self._update_best_headings()
        self._render_best()
