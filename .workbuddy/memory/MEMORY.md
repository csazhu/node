# 项目长期笔记：10v10AI 数据面板 (F:/github/node)

## 技术栈 / 构建
- `app.py` 是原生 tkinter 单文件应用（深色主题），`config.json` 存 refreshToken 等，`heroes.json` 存英雄名映射。
- 打包用 `D:\Python\Python310\python.exe -m PyInstaller --noconfirm --onefile --windowed --name dota-stats ... app.py`，
  再 `cp dist-py/dota-stats.exe ./dota-stats.exe`。系统 PATH 上的 `python`(3.13) 没装 tkinter / PyInstaller，
  所以 `build.bat` 直接用 `python` 会失败，必须用 Python310 解释器。
- 运行脚本 `run_exe.bat` / `run_py.bat` 会设置代理 `http://127.0.0.1:18080`。

## 等级规则（与网站接口阈值对齐，用户确认按「游戏显示的等级」口径）
- 会员：`need(L→L+1) = 1000 + 50*(L-1)`，累计 `cum(L) = 1000*(L-1) + 25*(L-1)*(L-2)`（MEMBER_STEP=50, MEMBER_BASE=1）。
  校验：20→21 需 1950，总经验 27550+550=28100 = memberPointTotal。
- 勇士：`need(L→L+1) = 1000 + 100*(L-10) = 100*L`，累计 `cum(L) = 50*L*(L-1)`（WARRIOR_STEP=100, WARRIOR_BASE=10）。
  校验：71→72 需 7100，总积分 248500+3211=251711 = seasonPointTotal。
- 用户口述的「0升1 1000 / 1升2 +50(或+100)」是升级次数编号，与接口显示等级差一个起点偏移。

## 业务口径
- 会员经验按每日签到 **100/天** 推算日期（可在会员表表头改），未计每月订阅 1000。
- 勇士积分：每把约 105（可改），每天任务奖励 `config.json` 的 `taskPoints` = 300，必须计入天数计算。
- 场均时长取 `/stats/recent` 的 durationSec 平均值，用于把局数换算成小时。
- 勇士表「是否是自己」默认勾选：起始等级置灰、按自己当前总积分起算；取消勾选则输入框置空由用户填（用户明确要求），等级按整级边界起算。

## 用户偏好
- 迭代方式：给出口径+排版要求，希望直接改代码并重打包 exe；细节（高度、默认值）由助手把控。
