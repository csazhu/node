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

## 4. 自动刷新与超时口径
- 启动即自动刷新；**一次刷新完成后等 5 秒**再发起下一轮（不是发起后计时），`RefreshController` 保证不并发、可开关、关窗即停。
- 单轮 = 1 次 Firebase token 刷新（id_token 缓存 50 分钟，通常不请求）+ 3 个业务接口。
- 超时评估：业务接口正常响应 < 1s，取 **5s** 容忍抖动；token 端点走境外代理，取 **10s**。原统一 30s 最坏 4×30=120s 假死，现最坏 10+3×5=25s（有缓存时 15s），失败 5s 后自动重试。
- `config.json` 可选覆盖：`apiTimeout`、`tokenTimeout`、`autoRefreshIntervalMs`（毫秒，默认 5000）。urllib 的 timeout 是单次 socket 操作超时，不是整轮总耗时。
- 接口失败不再静默：`collect()` 返回 `warnings`，状态栏显示；token 失败整轮报错并重试。
- **无感知刷新**：自动刷新不改鼠标光标（禁止 watch）、不反复改写状态栏（只显示错误/警告、首轮与手动刷新才给加载反馈），保留战绩表滚动位置、搜索词、排序状态；数据未变则跳过战绩表与会员表重建。手动「刷新」按钮仍显示「正在加载数据...」。
- **战绩表头排序**：点击三态循环「升序 ▲ → 降序 ▼ → 恢复原始顺序」，换列从升序开始；按 `SORT_KEYS` 里的原始数值排序（不用带千分位的显示字符串），排序状态跨自动刷新保持。

## 5. 业务口径（勿擅自修改）
- 会员：`need(L→L+1)=1000+50*(L-1)`，`cum(L)=1000*(L-1)+25*(L-1)*(L-2)`（MEMBER_STEP=50, MEMBER_BASE=1）。校验：20→21 需 1950；总经验 27550+550=28100 → 20 级。
- 勇士：`need(L→L+1)=100*L`，`cum(L)=50*L*(L-1)`（WARRIOR_STEP=100, WARRIOR_BASE=10）。校验：71→72 需 7100；总积分 248500+3211=251711 → 71 级。
- 用户口述「0升1 1000 / 1升2 +50」是升级次数编号，与接口显示等级差一个起点偏移。
- 会员预测按每日签到 100 经验（不计每月订阅 1000）；勇士每把约 105 分，且**必须计入**每日任务 `taskPoints`=300；场均时长取 recent 的 durationSec 均值。
- 勇士表「是否是自己」默认勾选：起始等级置灰、按自己当前总积分起算；取消勾选则输入框置空由用户填，按整级边界起算。

## 6. 规则清单（自动维护）
<!-- RULES:START -->
- R001 [2026-11-11] `上下文` 每轮会话先读 AGENTS.md，按 §7 索引按需定位代码，不重复通读大文件，以节约 token 与上下文
- R002 [2026-11-11] `规则维护` 产生新规则、口径、接口约定、命令变更或用户偏好时，必须在同一轮自动写入 §6 规则清单，并随本次改动一起提交 git
- R003 [2026-11-11] `开发流程` 每个新功能：实现 → 自测（未通过继续修复并重测，直到全绿）→ 本地 git commit（中文描述）→ 再打包 exe，顺序不可颠倒
- R004 [2026-11-11] `环境` 自测、运行、打包统一使用 Python310 解释器；PATH 上的 python 3.13 缺 tkinter 与 PyInstaller
- R005 [2026-11-11] `自动刷新` 接口自动刷新：一次刷新完成后等 5 秒再发起下一轮，不并发、可开关、关窗即停；超时 token 10s、业务接口 5s，可由 config.json 覆盖
- R006 [2026-11-11] `git` 提交描述使用中文，英文类型前缀（feat、fix 等）可以保留
- R007 [2026-11-11] `业务口径` §5 的等级公式与业务口径不得擅自修改，变更需先与用户确认
- R008 [2026-11-11] `安全` config.json 与 node.rar 含密钥，只放本机、禁止入库，git 历史已清除；exe、build-py、dist-py 及自动更新产物不入库；新增含密钥文件必须先加 .gitignore
- R009 [2026-11-11] `线程安全` 取数子线程只写结果队列，所有 tkinter 操作由主线程 _poll_results 轮询执行，禁止子线程调用 root.after 或控件方法
- R010 [2026-11-11] `无感知刷新` 自动刷新不得设置等待光标或反复改写状态栏；数据未变不重建战绩表与会员表，保留滚动位置、搜索词、排序状态；仅手动刷新给加载反馈
- R011 [2026-11-11] `战绩排序` 近期战绩表头点击三态循环：升序 → 降序 → 恢复原始顺序；换列从升序开始；按 SORT_KEYS 原始数值排序，排序状态跨自动刷新保持；标题右侧固定显示「点击可排序」提示，不再显示 `(最近 N 场)` 数量文案
- R012 [2026-11-11] `版本源` 客户端内置 APP_VERSION 与 CHANGELOG；GitHub main 分支根目录 version.json 是唯一服务器版本源（version / downloadUrl / releasePage / changelog）；发新版只改该文件并把 dota-stats.exe 作为同名 Release 附件上传并推送；config.json 可用 versionUrl 覆盖版本源、checkUpdate=0 关闭检查
- R013 [2026-11-11] `版本检查` 启动后子线程读版本清单、独立 _updates 队列由主线程轮询（遵守 R009）；失败或同版本静默跳过；仅远程版本更高时弹非模态可关闭提示窗，不强制更新，关闭后照常用当前版本
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
<!-- RULES:END -->

## 7. 代码索引（按需定位，别通读）
- `app.py`：`http_json` / `refresh_id_token` / `api_get`（HTTP+超时）→ `SORT_KEYS`（排序键）→ `DataFetcher.collect`（取数与 warnings）→ `RefreshController`（纯逻辑调度，无 tkinter 依赖）→ `App._begin_fetch` / `_poll_results` / `_finish` / `render`（子线程取数写队列、主线程轮询渲染、数据未变跳过重建）→ `_on_sort` / `_update_headings` / `apply_filter`（三态排序 + 过滤 + 滚动恢复）→ `_build_ui`（顶部自动刷新开关、可点击表头）。
- 等级公式 `level_need` / `level_cum` / `level_from_exp`；界面常量 `BG`…；入口 `main()`（启动后调用 `start_version_check`）。
- 版本与更新：`version_tuple` / `is_newer` / `fetch_version_info` / `new_changelog_entries` / `download_file` / `build_update_bat` / `apply_update`（纯逻辑）→ `_changelog_lines` / `_changelog_metrics` / `_render_changelog`（卡片文本、按内容估算高度、悬挂缩进）→ `ChangelogWindow` / `UpdateWindow`（深色卡片式弹窗，滚动条按需、按钮常驻底部；`ChangelogWindow` 的 `_arm_outside_close` / `_close_if_focus_left` 负责更新日志点击窗口外关闭，`App.btn_changelog` 是入口按钮引用）→ `App.start_version_check` / `_poll_updates` / `start_update` / `finish_update`（独立队列 + 主线程轮询）→ `_build_ui` 右上角版本号与「更新日志」按钮；服务器清单 `version.json`。
- `tests/test_app.py`（应用逻辑）、`tests/test_ui.py`（排序与无感知刷新的 GUI 行为）、`tests/test_version.py`（版本检查、下载替换、弹窗）、`tests/test_rules.py`（规则脚本）、`tools/rule.py`（规则清单维护）。

## 8. 用户偏好
- 迭代方式：给出口径 + 排版要求，直接改代码并重打包 exe；细节（高度、默认值）由助手把控。
- 密钥文件（config.json、node.rar）只放本地、不提交；仓库按公开口径维护。
