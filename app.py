"""10v10AI 数据面板 - 原生 Windows 窗口版（兼容门面）。

实现按职责拆分在 dota_stats 包内；本文件保留全部原有名称与入口，
使 `import app` / `from app import xxx` / `mock.patch.object(app, "xxx")`
的行为与拆分前完全一致。
"""

import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import types
import urllib.request
import urllib.parse
import webbrowser

import storage
from datetime import datetime, timedelta, timezone
from http.client import HTTPSConnection

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    print("需要 Python 3.8+，请先安装 Python（自带 tkinter）")
    sys.exit(1)

# ============ 对外兼容：重新导出拆分前的全部模块级名称 ============
from dota_stats.app_core import (
    App,
)
from dota_stats.config import (
    API_BASE,
    API_TIMEOUT,
    APP_DIR,
    APP_VERSION,
    AUTO_REFRESH_INTERVAL_MS,
    CHANGELOG,
    DOWNLOAD_TIMEOUT,
    FETCH_MAX_ATTEMPTS,
    FETCH_RETRY_INTERVAL_S,
    FETCH_SPIN_MS,
    FIREBASE_API_KEY,
    PREF_AUTO_REFRESH,
    TOKEN_CACHE_TTL,
    TOKEN_TIMEOUT,
    TOKEN_URL,
    UPDATE_BAT_NAME,
    UPDATE_EXE_NAME,
    UPDATE_NEW_NAME,
    VERSION_CHECK_MIN_INTERVAL_MS,
    VERSION_TIMEOUT,
    VERSION_URL,
    load_json,
)
from dota_stats.domain import (
    MEMBER_BASE,
    MEMBER_STEP,
    SORT_KEYS,
    WARRIOR_BASE,
    WARRIOR_STEP,
    _difficulty_sort_key,
    fmt_duration,
    get_game_date,
    level_cum,
    level_from_exp,
    level_need,
    local_time_str,
)
from dota_stats.network import (
    DataFetcher,
    FetchCancelled,
    RefreshController,
    UA,
    _build_opener,
    _opener,
    _proxy_host,
    api_get,
    fetch_with_retry,
    http_json,
    refresh_id_token,
)
from dota_stats.theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_SOFT,
    BADGE_ALERT_BG,
    BADGE_ALERT_HOVER,
    BG,
    BTN_HOVER,
    BTN_PRESSED,
    CHANGELOG_MAX_LINES,
    CHANGELOG_TEXT_WIDTH,
    DANGER,
    FAINT,
    FONT_NUM,
    FONT_UI,
    GOLD,
    LINE,
    MUTED,
    PANEL,
    PANEL_SOFT,
    S1,
    S2,
    S3,
    S4,
    S5,
    SUCCESS,
    TEXT,
    _changelog_lines,
    _changelog_metrics,
    _display_width,
    _divider,
    _render_changelog,
)
from dota_stats.updater import (
    apply_update,
    build_update_bat,
    download_file,
    fetch_version_info,
    is_newer,
    new_changelog_entries,
    version_tuple,
)
from dota_stats.windows import (
    ChangelogWindow,
    SyncWindow,
    UpdateWindow,
)


class _FacadeModule(types.ModuleType):
    """模块属性写入 -> 同步到实现模块。

    拆分后函数/常量定义在 dota_stats 子模块中，若测试或外部代码仍按老习惯
    ``mock.patch.object(app, "http_json", ...)`` 替换 app 模块的属性，
    这里把写入广播给所有持有同名全局的实现模块，保证替换立刻生效、退出时还原。
    """

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for mod in tuple(sys.modules.values()):
            if mod is None or not str(getattr(mod, "__name__", "")).startswith("dota_stats"):
                continue
            if hasattr(mod, name):
                try:
                    setattr(mod, name, value)
                except (AttributeError, TypeError):
                    pass


sys.modules[__name__].__class__ = _FacadeModule

def main():
    root = tk.Tk()
    try:
        # 高 DPI 适配
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App(root)
    app.start_version_check()
    root.mainloop()


if __name__ == "__main__":
    main()
