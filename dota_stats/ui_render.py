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
        """按每天固定会员经验，推算未来 100 级的达成日期；一行 2 个"""
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
        items = []
        for i in range(1, 101):
            lv = cur + i
            need = level_cum(lv, MEMBER_STEP, MEMBER_BASE) - total
            days = max(0, math.ceil(need / daily))
            items.append((lv, (today + timedelta(days=days)).strftime("%Y-%m-%d")))

        for r in range(0, 100, 2):
            bg = PANEL if (r // 2) % 2 else PANEL_SOFT
            row = tk.Frame(self.mem_list, bg=bg)
            row.pack(fill="x")
            for j in range(2):
                lv, d = items[r + j]
                cell = tk.Label(
                    row,
                    text=f"{lv}级  {d}",
                    bg=bg,
                    fg=TEXT,
                    font=(FONT_NUM, 11),
                    anchor="w",
                    width=21,
                )
                cell.grid(row=0, column=j, sticky="w", padx=(0, 10))
                self._make_selectable(cell)

        self.mem_canvas.yview_moveto(view[0])
        self.mem_summary.config(
            text=(
                f"当前 {cur} 级 · 总经验 {total:,} · 本级 "
                f"{self.profile.get('memberCurrPoint', 0):,}/{self.profile.get('memberNextPoint', 0):,}"
                f" · 按每天 {daily:g} 经验\n"
                f"{cur + 1}~{cur + 100} 级达成日期（最近一级 {items[0][1]}；仅计每日签到，可在上方修改）"
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
                    font=(FONT_NUM, 12), anchor="center", pady=6,
                )
                lbl.grid(row=0, column=i, sticky="ew")
                self._make_selectable(lbl)
            tk.Frame(frame, bg=LINE, height=1).pack(fill="x")
        frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _render_days(self):
        self._render_stats_rows(
            self.day_rows_frame, self.day_cols_def, self.days, self.day_canvas
        )

    def _render_months(self):
        self._render_stats_rows(
            self.month_rows_frame, self.month_cols_def, self.months, self.month_canvas
        )

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

    def apply_filter(self):
        """近期战绩：按英雄筛选（觉醒 / 非觉醒视为同一英雄）+ 三态排序。"""
        q = self.hero_filter_var.get().strip().lower()
        if q and q != "全部英雄":
            rows = [r for r in self.rows if q in r["hero"].lower()]
        else:
            rows = list(self.rows)
        self._fill_tree(self.tree, rows, self.sort_col, self.sort_state)
        self._update_headings()

    # ================= 英雄筛选（可打字搜索的下拉框） =================
    def _refresh_hero_options(self):
        """用当前全部英雄刷新下拉列表；保留用户已选/已输入，除非已无任何英雄匹配。"""
        heroes = sorted({r["hero"] for r in self.rows})
        self.heroes_list = heroes
        cur = self.hero_filter_var.get().strip()
        if cur and cur != "全部英雄" and not any(cur.lower() in h.lower() for h in heroes):
            self.hero_filter_var.set("全部英雄")
        self.hero_filter["values"] = ["全部英雄"] + heroes

    def _on_hero_filter(self, event=None):
        """从下拉点选：还原完整列表（保留当前选择）并重算筛选。"""
        self._refresh_hero_options()
        self.apply_filter()

    def _on_hero_filter_typing(self, event=None):
        """打字时实时收窄下拉内容，并按输入子串筛选战绩表。"""
        q = self.hero_filter_var.get().strip().lower()
        if q and q != "全部英雄":
            opts = ["全部英雄"] + [h for h in self.heroes_list if q in h.lower()]
        else:
            opts = ["全部英雄"] + self.heroes_list
        self.hero_filter["values"] = opts
        self.apply_filter()

    # ================= 最佳战绩：每英雄 × 每难度取用时最短一条 =================
    def _render_best(self):
        """全量数据（self.rows）里，每个英雄在 n6/n7/n8 各取用时最短（durationSec 最小）的一条。

        难度筛选（默认 N8）决定展示哪一难度；「全部(N6-N8)」则每个英雄列三行。
        觉醒 / 非觉醒是同一英雄（hero 字段已不含觉醒），按 hero 聚合即可。
        """
        diff = self.best_diff_var.get()
        allowed = {"N6", "N7", "N8"} if diff == "全部(N6-N8)" else {diff}
        best = {}
        for r in self.rows:
            d = r["difficulty"]
            if d not in allowed:
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
