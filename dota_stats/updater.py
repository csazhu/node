"""版本与自动更新：版本比较、清单读取、下载校验、替换脚本生成。"""

import json
import os
import re
import subprocess
import urllib.request
import urllib.parse
from .config import APP_DIR, APP_VERSION, DOWNLOAD_TIMEOUT, UPDATE_BAT_NAME, UPDATE_EXE_NAME, VERSION_TIMEOUT, VERSION_URL
from .network import UA, _opener, http_json


# ================= 版本 / 更新（纯逻辑，可离线测试） =================
def version_tuple(text):
    """'v1.2.3' / '1.2' → (1, 2, 3)；忽略非数字段，最多取 4 段。"""
    nums = [int(x) for x in re.findall(r"\d+", str(text or ""))][:4]
    return tuple(nums) if nums else (0,)


def is_newer(remote, local):
    """服务器版本是否高于本地版本；位数不足补 0，1.2 == 1.2.0。"""
    r, l = version_tuple(remote), version_tuple(local)
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def fetch_version_info(url=VERSION_URL, timeout=VERSION_TIMEOUT):
    """读取服务器版本清单；也接受本地路径 / file:// 便于离线验证。"""
    path = url[7:] if url.startswith("file://") else url
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return http_json(url, timeout=timeout)


def new_changelog_entries(info, local_version=APP_VERSION):
    """取服务器 changelog 里比本地版本新的条目，按版本降序。"""
    entries = [
        e for e in (info or {}).get("changelog", [])
        if is_newer(e.get("version"), local_version)
    ]
    return sorted(entries, key=lambda e: version_tuple(e.get("version")), reverse=True)


def download_file(url, dest, progress=None, timeout=DOWNLOAD_TIMEOUT, chunk=65536):
    """下载更新包并校验 PE 头（MZ），避免把 404 页面写成 exe。

    必须一次性 read() 读完响应体再分块写盘：经代理逐块 read(chunk) 时每块
    都要等一次网络往返，9 MB 实测约 279 秒；一次性读取约 8 秒。
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/octet-stream"})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            total = int(resp.headers.get("Content-Length") or 0) or len(data)
        with open(dest, "wb") as f:
            done = 0
            for start in range(0, len(data), chunk):
                piece = data[start:start + chunk]
                f.write(piece)
                done += len(piece)
                if progress:
                    progress(done, total)
            if not data and progress:
                progress(0, total)
        with open(dest, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("下载内容不是有效的 Windows 程序，已放弃更新")
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    return dest


def build_update_bat(pid, target, new):
    """纯 ASCII 替换脚本：路径靠 %~dp0 展开，放在中文目录下也不会乱码。

    主进程退出前 move 会失败，循环重试直到 exe 可覆盖，再启动新版本并自删。
    """
    return "\r\n".join([
        "@echo off",
        "setlocal",
        'cd /d "%~dp0"',
        f"set PID={int(pid)}",
        f"set TARGET={target}",
        f"set NEW={new}",
        "set /a N=0",
        ":wait",
        'move /Y "%NEW%" "%TARGET%" >nul 2>&1',
        "if not errorlevel 1 goto ok",
        "ping -n 2 127.0.0.1 >nul",
        "set /a N+=1",
        "if %N% LSS 60 goto wait",
        "echo Replace failed. Rename %NEW% manually. > update-error.log",
        'del "%~f0"',
        "exit /b 1",
        ":ok",
        'start "" "%TARGET%"',
        'del "%~f0"',
        "exit /b 0",
        "",
    ])


def apply_update(new_path, target_path=None, pid=None):
    """写替换脚本并拉起；调用方随后关闭主窗口即可完成覆盖 + 重启。"""
    target_path = target_path or os.path.join(APP_DIR, UPDATE_EXE_NAME)
    pid = os.getpid() if pid is None else pid
    bat = os.path.join(APP_DIR, UPDATE_BAT_NAME)
    with open(bat, "w", encoding="ascii", newline="") as f:
        f.write(build_update_bat(pid, os.path.basename(target_path), os.path.basename(new_path)))
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd.exe", "/c", bat], cwd=APP_DIR, **kwargs)
    return bat
