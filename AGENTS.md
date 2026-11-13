# AGENTS.md — 10v10AI 数据面板 / AI 协作约定

> **唯一规则源**。每轮会话开始先读本文件；按 §7 索引按需定位代码，不要重复通读 app.py 等大文件。
> 目标：节省 token，把上下文留给本次改动。规则以本文件为准，`.workbuddy/memory/MEMORY.md` 只保留指针。

## 0. 维护协议（最高优先级）
- 出现**新规则 / 业务口径 / 接口约定 / 命令变更 / 用户偏好**时，必须在**同一轮**写入 §6 规则清单并随本次改动一起提交 git，不允许只留在对话里。
- 写入命令：`D:\Python\Python310\python.exe tools/rule.py add "规则正文" [--tag 分类]`（自动编号、去重、带日期）；也可直接编辑 §6，保持 `- Rnnn [日期] 正文` 格式。
- 规则过时就地改写或删除，不追加重复条目；本文件保持精简（约 120 行内），过程记录交给 git log。
- 每次提交前自检：§2 命令、§3 流程、§4 实现、§7 索引是否与本次改动一致。

## 1. 项目速览
- 单文件 tkinter 深色桌面应用 `app.py`；`config.json`（refreshToken 等，**只放本机、不入库**），`heroes.json`（英雄名映射）。仓库 `csazhu/node` 按 Public 口径维护（客户端依赖匿名直链）。
- 数据源：Firebase refreshToken → id_token → `https://windy10v10ai.com/api/player/{userId}/…`。运行脚本会设代理 `http://127.0.0.1:18080`。
- 版本源：仓库根目录 `version.json`（服务器版本清单，发版维护；不随 exe 打包）；客户端内置 `APP_VERSION` / `CHANGELOG`。
- 打包产物 `dota-stats.exe`（不入库）。

## 2. 环境与命令（Windows / Git Bash）
- 解释器：**必须用 `D:\Python\Python310\python.exe`**（PATH 上的 `python` 是 3.13，缺 tkinter 与 PyInstaller）。
- 运行：`run_py.bat`（源码）/ `run_exe.bat`（exe），均带代理环境变量。
- 自测：`D:\Python\Python310\python.exe -m unittest discover -s tests -v`
- 打包：`build.bat`（内部已固定 Python310），等价于 `-m PyInstaller --noconfirm --onefile --windowed --name dota-stats --distpath dist-py --workpath build-py --specpath . app.py` + 复制 exe 到根目录。
- git：提交描述用中文（英文类型前缀如 `feat:` 可保留）。访问 GitHub 须显式走 `http://127.0.0.1:18080` 代理（环境变量默认指向 60182，会 schannel TLS 握手失败）；凭证由 Windows Credential Manager 提供。

## 3. 开发流程（强制，顺序不可颠倒）
1. 实现功能。
2. **自测**：跑 §2 的自测命令；未通过 → 修复 → 重跑，直到全部通过。不允许跳过或带着失败继续。
3. 测试通过后 `git add` + **本地 git commit**（中文描述）。
4. commit 之后才**打包 exe**，并确认产物生成。
> 禁止：测试未过就提交/打包、先打包再提交、把 exe 或 config.json 的密钥改动提交进仓库。

## 4. 取数重试 / 自动刷新与超时口径
- 启动即取一轮（延迟到事件循环）：3 个业务接口各起独立 daemon 线程并行，**取到成功数据即止**；失败最多尝试 **5 次**、每次失败间隔 **0.5 秒**；5 次仍失败的接口本轮静默跳过并保留旧内容。
- 自动刷新**默认不开启**：顶栏「刷新」按钮左下方小字「自动刷新」小勾默认不勾，默认取完启动那一轮就停；勾上才由 `RefreshController` 在**一轮完成后等 5 秒**发起下一轮（不是发起后计时），不并发、关窗即停。
- 点「刷新」**立刻启动一组新线程**（不等定时器），同样 5 次重试；新组抢占旧组（`cancel` 事件置位、旧线程快速退出、旧结果按 `seq` 丢弃），同一时刻只有一组在跑；本组未结束前重复点击无效，按钮显示旋转「◐ 刷新中」特效，收尾即关闭这组线程并恢复按钮。自动轮不显示特效、保持无感知。
- 单轮 = 1 次 Firebase token 刷新（id_token 缓存 50 分钟，通常不请求）+ 3 个业务接口并行；token 刷新失败清缓存，保证线程内重试能重新取凭证。
- 超时评估：业务接口正常响应 < 1s 取 **5s**；token 端点走境外代理取 **10s**。urllib 的 timeout 是单次 socket 操作超时，不是整轮总耗时。
- `config.json` 可选覆盖：`apiTimeout`、`tokenTimeout`、`autoRefreshIntervalMs`（毫秒，默认 5000）、`autoRefresh`（0/1，默认 0）、`fetchMaxAttempts`（默认 5）、`fetchRetryIntervalMs`（毫秒，默认 500）。
- **无感知刷新**：自动轮不改鼠标光标（禁止 watch）、不反复改写状态栏、保留滚动位置/搜索词/排序状态；数据未变跳过重建；接口失败静默（R034）。仅首轮显示「正在加载数据...」，手动轮的反馈只走按钮特效、不动状态栏。
- **战绩表头排序**：点击三态循环「升序 ▲ → 降序 ▼ → 恢复原始顺序」，换列从升序开始；按 `SORT_KEYS` 里的原始数值排序（不用带千分位的显示字符串），排序状态跨自动刷新保持。

## 5. 业务口径（勿擅自修改）
- 会员：`need(L→L+1)=1000+50*(L-1)`，`cum(L)=1000*(L-1)+25*(L-1)*(L-2)`（MEMBER_STEP=50, MEMBER_BASE=1）。校验：20→21 需 1950；总经验 27550+550=28100 → 20 级。
- 勇士：`need(L→L+1)=100*L`，`cum(L)=50*L*(L-1)`（WARRIOR_STEP=100, WARRIOR_BASE=10）。校验：71→72 需 7100；总积分 248500+3211=251711 → 71 级。
- 用户口述「0升1 1000 / 1升2 +50」是升级次数编号，与接口显示等级差一个起点偏移。
- 会员预测按每日签到 100 经验（不计每月订阅 1000）；勇士每把约 105 分，且**必须计入**每日任务 `taskPoints`=300；场均时长取 recent 的 durationSec 均值。
- 勇士表「是否是自己」默认勾选：起始等级置灰、按自己当前总积分起算；取消勾选则输入框置空由用户填，按整级边界起算；**升到等级默认 = 起始等级 +10**（仅当用户未手动填写时填充，自动刷新不覆盖已改值；显式取消勾选则清空两个等级框）。

## 6. 规则清单（自动维护）
<!-- RULES:START -->
- R001 [2026-11-11] `上下文` 每轮会话先读 AGENTS.md，按 §7 索引按需定位代码，不重复通读大文件，以节约 token 与上下文
- R002 [2026-11-11] `规则维护` 产生新规则、口径、接口约定、命令变更或用户偏好时，必须在同一轮自动写入 §6 规则清单，并随本次改动一起提交 git
- R003 [2026-11-11] `开发流程` 每个新功能：实现 → 自测（未通过继续修复并重测，直到全绿）→ 本地 git commit（中文描述）→ 再打包 exe，顺序不可颠倒
- R004 [2026-11-11] `环境` 自测、运行、打包统一使用 Python310 解释器；PATH 上的 python 3.13 缺 tkinter 与 PyInstaller
- R005 [2026-11-13] `自动刷新` 自动刷新默认关闭：顶栏「刷新」按钮左下方「自动刷新」小勾默认不勾，取完启动那一轮即停；勾上才由 RefreshController 在一轮完成后等 5 秒续跑，不并发、关窗即停；config.json 的 autoRefresh=1 可改默认；超时 token 10s / 业务接口 5s，间隔可用 autoRefreshIntervalMs 覆盖
- R006 [2026-11-11] `git` 提交描述使用中文，英文类型前缀（feat、fix 等）可以保留
- R007 [2026-11-11] `业务口径` §5 的等级公式与业务口径不得擅自修改，变更需先与用户确认
- R008 [2026-11-11] `安全` config.json 与 node.rar 含密钥，只放本机、禁止入库，git 历史已清除；exe、build-py、dist-py 及自动更新产物不入库；新增含密钥文件必须先加 .gitignore
- R009 [2026-11-11] `线程安全` 取数子线程只写结果队列，所有 tkinter 操作由主线程 _poll_results 轮询执行，禁止子线程调用 root.after 或控件方法
- R010 [2026-11-13] `无感知刷新` 自动轮不得设置等待光标或反复改写状态栏；数据未变不重建战绩表与会员表，保留滚动位置、搜索词、排序状态；仅首轮给「正在加载数据...」反馈，手动轮的反馈只走按钮「刷新中」旋转特效、不动状态栏（R039）
- R011 [2026-11-11] `战绩排序` 近期战绩表头点击三态循环：升序 → 降序 → 恢复原始顺序；换列从升序开始；按 SORT_KEYS 原始数值排序，排序状态跨自动刷新保持；标题右侧固定显示「点击可排序」提示，不再显示 `(最近 N 场)` 数量文案
- R012 [2026-11-11] `版本源` 客户端内置 APP_VERSION 与 CHANGELOG；GitHub main 分支根目录 version.json 是唯一服务器版本源（version / downloadUrl / releasePage / changelog）；发新版只改该文件并把 dota-stats.exe 作为同名 Release 附件上传并推送；config.json 可用 versionUrl 覆盖版本源、checkUpdate=0 关闭检查
- R013 [2026-11-12] `版本检查` 启动后子线程读 version.json、独立 _updates 队列由主线程轮询（遵守 R009）；不主动弹任何更新窗口：右上角版本徽章常驻显示当前版本与服务器最新版本，并有检查中/已是最新/检查失败/未检查状态；仅远程版本更高时亮红点 + 红框 + 「点击更新」，用户点徽章才打开非模态可关闭的 UpdateWindow，不强制更新、不自动下载
- R014 [2026-11-11] `自动更新` 点「立即更新」后台下载到 dota-stats.new.exe 并校验 MZ 头；点「重启并完成更新」后由纯 ASCII 的 _apply_update.bat 等主进程退出后覆盖 exe 并重启；源码运行模式降级为打开下载页
- R015 [2026-11-11] `更新日志` 右上角「更新日志」展示本地内置 CHANGELOG（离线可用）并显示当前版本号；服务器 changelog 只用于新版本提示窗
- R016 [2026-11-11] `仓库口径` node 仓库按 Public 口径维护，客户端依赖 raw.githubusercontent.com 的 version.json 与 /releases/latest/download/dota-stats.exe 两条匿名直链，版本清单与 Release 附件必须可匿名访问；仓库曾含密钥历史，改公开前须清史并 force push
- R017 [2026-11-11] `发版顺序` 发版顺序：同步改 APP_VERSION / CHANGELOG / version.json → 自测全绿 → 本地 commit（**先不 push**）→ 打包 → 建 Release 上传同名 dota-stats.exe → 最后才 push 该 commit 让服务器 version.json 生效；服务器版本号早于 Release 就绪会弹窗却下载 404，version.json 与 exe 内置版本不一致会更新后仍提示形成死循环
- R018 [2026-11-11] `代理` git 访问 GitHub 时须显式覆盖代理为 http://127.0.0.1:18080（env HTTPS_PROXY=... HTTP_PROXY=... git push）；环境变量默认指向 60182 是 WorkBuddy 内部代理，git 走它会报 schannel TLS 握手失败
- R019 [2026-11-11] `更新性能` 启动版本检查超时取 10 秒（子线程执行，不阻塞启动；冷启动首请求实测 5.22s，5 秒会被静默跳过）；下载更新包必须一次性 resp.read() 读完响应体再分块写盘，禁止 read(chunk) 循环——经 18080 代理逐块读 9 MB 需约 279 秒，一次性读取约 8 秒
- R020 [2026-11-11] `发版API` 发版可用 git credential fill 取出缓存的 GitHub PAT 调 REST API：POST /repos/csazhu/node/releases 建 Release、POST uploads.github.com/.../assets?name=dota-stats.exe 传附件；make_latest 必须传字符串 'true' 而非布尔值；匿名 api.github.com 有 IP 限流会 403，验证匿名直链须用 curl 走 18080 代理
- R021 [2026-11-11] `安全` force push 覆盖远端不等于清除 GitHub 上的旧对象：仓库转 Public 后旧 commit SHA 仍可匿名访问其树内文件（实测 raw@37c9b76/config.json 返回 200，且含当前有效 refreshToken）；凡曾入库的密钥必须先轮换再改公开，彻底移除旧对象只能删库重建或联系 GitHub Support，仅从 main 删除文件不能保密
- R022 [2026-11-11] `弹窗排版` 「发现新版本」与「更新日志」共用卡片式窗口：由 _changelog_metrics 按内容估算 Text 高度（上限 16 行）并按需显示滚动条，禁止固定 560x460 导致大片空白、操作按钮被挤出屏幕；版本行高亮、条目用 tag 悬挂缩进（lmargin2）而非空格模拟列表；大标题用版本对比避免与窗口标题重复，主按钮强调色且按钮区常驻底部
- R023 [2026-11-11] `弹窗交互` 「更新日志」窗口启用点击窗口外关闭：延迟 150ms 绑定自身 <FocusOut> 与主窗口 <ButtonPress-1> 双保险，after_idle 判断焦点归属后 destroy；焦点仍在窗口内或落在「更新日志」按钮上不关，重复点击按钮复用窗口；「发现新版本」提示窗不启用以免误点打断下载。主窗口绑定须用 bind(add='+') 记录追加脚本片段并精确摘除，禁止 widget.unbind(seq, funcid)（会清空主窗口该事件的全部绑定）
- R024 [2026-11-11] `接口独立性` 三个业务接口（排行榜 / 会员赛季资料 / 近期战绩）各自独立成败：collect 记录 failed 清单，render 仅合并成功接口数据到持久状态，失败接口保留上一轮旧内容不更新；界面 7 区块映射为——排行榜排名←排行榜接口，赛季等级/距下一级经验/会员等级/总场次←会员赛季资料接口，每日统计/近期战绩←近期战绩接口
- R025 [2026-11-12] `界面配色` clam 主题 ttk 控件默认 active 背景近白色 #eeebe7，只 style.configure 改不掉状态映射会白底白字；_build_ui 必须成对覆盖 TButton 与 Update.TButton 的 active/pressed/disabled 背景与前景（深色底浅色字），_style_tree 覆盖表头 active 与选中行前景；新增 ttk 控件一律检查 hover/selected 对比度
- R026 [2026-11-12] `版本徽章` 右上角版本徽章用 tk 控件逐个上色，当前版本与服务器最新版本常驻显示；红点与提示位固定宽度常驻，状态切换不得改变徽章宽度导致顶栏跳动；悬停只换成更亮的深色底，文字保持浅色
- R027 [2026-11-12] `界面设计` 界面设计系统：深色桌面界面统一按「暖墨色中性面 + 唯一琥珀强调色 ACCENT」设计 DNA——BG/PANEL/PANEL_SOFT 三级表面、LINE 1px 细线、TEXT/MUTED/FAINT 三级文字、S1~S5 8pt 间距、FONT_UI/FONT_NUM 字体 token；色彩 60-30-10，强调色只用于主按钮/焦点/关键数值/状态灯；禁止渐变、阴影、卡片套卡片，新增控件一律复用 token 与 ttk 样式名，不硬编码色值与字体
- R028 [2026-11-13] `界面设计` 界面结构：顶栏右侧保留 Ghost.TButton（更新日志）、版本徽章与 Primary.TButton「刷新」按钮（R039 加回），刷新按钮左下方为默认不勾的「自动刷新」小字勾选行；按钮固定 width=10，切换「◐ 刷新中」时顶栏不跳动；并成对覆盖 clam 的 active/pressed/disabled 状态映射（含 Primary/Ghost，避免白底白字）；状态栏必须先 pack(side='bottom') 再 pack 主体，否则内容过高会把状态栏挤出窗口；概览卡为单块面板 + 卡内 1px 竖线（cards_frame 直接子控件恒为 4）；战绩表带 1px 外框与水平/垂直滚动条，1400x900 默认窗口下列宽总和约 838px 使 12 列全部可见
- R029 [2026-11-12] `设计技能` 设计技能：界面优化使用已安装的用户级技能 ui-design-system 与 impeccable（UI Audit & Optimization Protocol 六维审查）；设计上下文持久化在 AGENTS.md §9，不新建 .impeccable.md（AGENTS.md 是唯一规则源）
- R030 [2026-11-12] `版本检查` 自动刷新每轮静默顺带查服务器版本（最小间隔 5 分钟，受 checkUpdate 开关与在途保护），不把徽章置为检查中、不闪烁；启动仍立即查一次
- R031 [2026-11-12] `写入优化` 自动刷新写入前先比对：所有接口数据与上次写入内容一致（排除 updatedAt 时间戳）则跳过重绘；版本徽章状态与上次写入一致则跳过；仅不一致才写入，避免每轮无谓重绘/闪烁
- R032 [2026-11-12] `写入优化` 每日统计聚合表（data.days）在 render 中先比对上次写入的 self.days，一致则跳过重绘；与版本徽章、概览卡片、会员表同属无感知更新：数据/版本变动才写入，否则不重绘不闪烁
- R033 [2026-11-13] `取数架构` 取数为可抢占线程组（R045）：每组 3 个 daemon 线程各取排行榜/会员赛季资料/近期战绩，成功即止、失败最多 5 次且间隔 0.5s；组带自增 seq 与 cancel Event，新组抢占旧组、旧结果按 seq 丢弃；子线程只入队，主线程 _poll_results 按接口独立比对、独立更新对应区块；版本号走独立 _maybe_refresh_version 线程；不做串行 collect 再整页重绘
- R034 [2026-11-12] `状态栏` 状态栏（左下角）不显示接口请求失败信息：某接口失败时静默保留上一轮旧内容、下一轮自动重试，不写「部分接口失败」等提示、状态灯不转红；保持无感知刷新
- R035 [2026-11-12] `回复` 所有面向用户的回复一律使用中文
- R036 [2026-11-12] `版本检查` 版本自动检查失败时，徽章旁显示「重试检查」按钮（平时隐藏不占位，仅 failed 态显示）；点击该按钮或点徽章均触发 _check_version(show_checking=True) 手动重试
- R037 [2026-11-12] `弹窗交互` 「更新日志」点击窗口外关闭的判定改为基于「点击目标的组件层级」而非焦点：点的是主窗口内任意组件（排行榜卡片/表头/按钮等，含默认不抢焦点的 ttk 标签）即关闭；点的是更新日志窗口自身或「更新日志」按钮不关。原因：ttk 标签/卡片默认 takefocus=False，点击时焦点仍停留在弹窗，单看焦点会误判成「窗口内」导致点排行榜关不掉
- R038 [2026-11-13] `勇士默认` 勇士等级计算「升到等级」默认 = 起始等级 +10：勾选「是自己」时按自己等级+10 填充；未勾选且保留手动值时起始有填、升到为空也按起始+10 给默认；仅当用户未手动填写才填充，自动刷新不覆盖已改值；显式取消勾选则清空两个等级框
- R039 [2026-11-13] `手动刷新` 顶栏「刷新」按钮已加回（v1.1.7 曾移除）：常驻可点的 Primary.TButton，左下方小字「自动刷新」勾选行默认不勾（R005）；`App.refresh` 立刻起一组新线程、`_manual_busy` 防重入（本组未结束重复点击无效）、`_start_spin` 显示「◐ 刷新中」旋转特效，收尾关闭这组线程并恢复按钮；自动轮不显示特效（R010）
- R040 [2026-11-13] `界面` 概览卡「距下一级还差 X」数值放大并改用强调色 ACCENT（`CardSubNum` 样式，FONT_NUM 14 粗体），与「还差」前缀形成层级；每日统计内容字号 12→14（表头 11→12 配平）。发版 v1.1.7：APP_VERSION / CHANGELOG / version.json 同步；勇士「升到等级」默认起始+10（R038）、当时移除刷新按钮（现已按 R039 加回）随本次发布
- R041 [2026-11-13] `界面` 概览卡高度固定：启动时即建好 4 张固定骨架（排行榜/赛季/会员/总场次），数据到了只原地更新文字、不销毁重建；副文本行用空格占位（ttk.Label 空 text 会塌缩到 1px，空格保留整行高度），确保加载前/加载后/缺数据三种状态 `cards_frame` 高度一致，避免数据加载后整页跳动
- R042 [2026-11-13] `渲染校验` 改 `_render_*` 时务必确认循环体缩进正确：v1.1.7 改每日统计字号时把 `lbl = tk.Label(...)`/`lbl.grid`/`self._make_selectable` 误移出 `for` 循环，导致每行只生成最后一列（效率），其余 4 列空白；单测「能跑通」拦不住，必须校验每行实际生成的单元格数量或肉眼看渲染。已加 `test_daily_stats_renders_all_columns_per_row` 回归测试
- R043 [2026-11-13] `发版` 发版 v1.1.8：APP_VERSION / CHANGELOG / version.json 同步；随本次发布带出概览卡高度固定（R041）与每日统计 4 列空白回归修复（R042）两项本地未推送的修复
- R044 [2026-11-13] `历史战绩接口` /api/player/{userId}/stats/history 是 recent（固定最近 50 场、hasMore=true、忽略 page/limit/offset）之外的历史战绩接口：默认返回 {matches, nextPage}，matches 为最近一个时间窗口内的全部场次（实测 80~87 场、约 7 天，因账号而异，与 recent 零重叠）；按 ?page=nextPage 翻页，每页 50 场、页码递减至 1（nextPage=null 到底），page=0 为空，page 超过该账号最大页时截断回最大页（默认窗口已含最后一页，故 nextPage 会跳过它，不会漏数据）；字段与 recent 完全一致可直接复用 derive_rows_days，matchId 多为字符串 "0" 去重须用 endedAt；接口免 Bearer 鉴权也可读，但仍按路径 userId 过滤（换 userId 返回各自的记录、交集为 0，不存在的 ID 返回空），记录无玩家 ID 字段且 endedAt 全唯一，均为该玩家个人单局表现；recent 的 50 场上限会把边界游戏日从中间截断，history 可补齐当日更早场次（实测本机 11-04：5 场/536 分/57 分 → 20 场/2469 分/3时56分，其余重叠日期逐日统计完全相同）
- R045 [2026-11-13] `取数重试` 单接口重试由 `fetch_with_retry` 统一实现：成功即返回、失败最多 FETCH_MAX_ATTEMPTS=5 次、每次失败等 FETCH_RETRY_INTERVAL_S=0.5s（cancel.wait 被抢占时立即唤醒并抛 FetchCancelled）；config.json 可用 fetchMaxAttempts / fetchRetryIntervalMs（毫秒）覆盖；自动刷新默认关闭用 autoRefresh（0/1）；token 刷新失败清缓存，避免重试反复拿过期凭证；回归见 tests/test_app.py::TestFetchRetry 与 tests/test_ui.py 手动刷新系列
<!-- RULES:END -->

## 7. 代码索引（按需定位，别通读）
- `app.py`：`http_json` / `refresh_id_token` / `api_get`（HTTP+超时）→ `SORT_KEYS`（排序键）→ `DataFetcher.fetch_*` / `collect`（单接口取数与串行兜底）→ `fetch_with_retry` / `FetchCancelled`（单接口 5 次重试、0.5s 间隔、抢占取消）→ `RefreshController`（纯逻辑调度，无 tkinter 依赖）→ `App._begin_fetch(manual)` / `_poll_results(seq)` / `_finish_round` / `_finish` / `render`（线程组取数写队列、主线程按 seq 轮询渲染、数据未变跳过重建）→ `App.refresh` / `_on_auto_toggle` / `_start_spin` / `_tick_spin` / `_stop_spin`（手动刷新抢占、自动刷新勾选、刷新中特效）→ `_on_sort` / `_update_headings` / `apply_filter`（三态排序 + 过滤 + 滚动恢复）→ `_build_ui`（设计 token 样式、顶栏 Primary/Ghost 分层 + 刷新按钮/自动刷新勾选行、状态栏先占底部、左列滚动、战绩表双向滚动、可点击表头、clam 状态映射覆盖、版本徽章）→ `_divider` / `_render_cards` / `_render_days` / `_style_tree` / `_render_member_table` / `_render_warrior`（1px 细线、卡片、斑马纹表格、2×2 输入）→ `_build_version_badge` / `_set_version_badge` / `_paint_badge` / `_on_version_click`（徽章构建、状态切换、悬停底色、手动点开更新）。
- 等级公式 `level_need` / `level_cum` / `level_from_exp`；界面设计 token `BG` / `PANEL` / `PANEL_SOFT` / `LINE` / `TEXT` / `MUTED` / `FAINT` / `ACCENT` / `S1~S5` / `FONT_UI` / `FONT_NUM`（口径见 §9）；入口 `main()`（启动后调用 `start_version_check`）。
- 版本与更新：`version_tuple` / `is_newer` / `fetch_version_info` / `new_changelog_entries` / `download_file` / `build_update_bat` / `apply_update`（纯逻辑）→ `_changelog_lines` / `_changelog_metrics` / `_render_changelog`（卡片文本、按内容估算高度、悬挂缩进）→ `ChangelogWindow` / `UpdateWindow`（深色卡片式弹窗，滚动条按需、按钮常驻底部；`ChangelogWindow` 的 `_arm_outside_close` / `_close_if_focus_left` 负责更新日志点击窗口外关闭，`App.btn_changelog` 是入口按钮引用）→ `App.start_version_check` / `_poll_updates` / `_on_update_version` / `start_update` / `finish_update`（独立队列 + 主线程轮询，版本事件只更新徽章不弹窗）→ `App._show_update_window` 仅由徽章点击触发；界面常量 `BTN_HOVER` / `BTN_PRESSED` / `BADGE_ALERT_BG`；服务器清单 `version.json`。
- `tests/test_app.py`（应用逻辑、RefreshController、TestFetchRetry 重试口径、GUI 冒烟）、`tests/test_ui.py`（排序、无感知刷新、手动刷新按钮/勾选/特效与旧组结果丢弃的 GUI 行为）、`tests/test_version.py`（版本检查、下载替换、弹窗）、`tests/test_rules.py`（规则脚本）、`tools/rule.py`（规则清单维护）。

## 8. 用户偏好
- 迭代方式：给出口径 + 排版要求，直接改代码并重打包 exe；细节（高度、默认值）由助手把控。
- 密钥文件（config.json、node.rar）只放本地、不提交；仓库按公开口径维护。
- 更新提示不要主动弹窗打扰；用右上角红点等显眼标记引导手动点击（2026-11-12）。

## 9. 设计上下文（UI 设计系统技能）
- 用户与场景：Dota 10v10AI 玩家本人，桌面端长时间挂机查看；关注排名、等级进度、近期战绩明细，5 秒自动刷新时不能打断阅读。
- 品牌调性：冷静、精确、专业，电竞数据终端感；不卖萌、不堆装饰。
- 审美方向：深色暖墨中性面 + 单一琥珀强调色，编辑式排版、数字优先、留白与细线建立层级。反参考：GitHub 默认蓝灰深色、AI 味青蓝发光渐变、万物皆卡片。
- 设计原则：① 一个视觉焦点（首卡琥珀短线 + 刷新主按钮）② 层级靠亮度与字号，不靠阴影/渐变 ③ 组件状态完整且深色下可读（WCAG AA）④ 数据密度优先、间距遵循 8pt 网格 ⑤ 强调色占 10% 以内。
