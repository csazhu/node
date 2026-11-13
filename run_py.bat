@echo off
chcp 65001 >nul
rem 代理已写入 config.json 的 proxy，源码运行同样由程序启动时自行设置
"D:\Python\Python310\python.exe" "%~dp0app.py"
pause
