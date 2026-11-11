@echo off
chcp 65001 >nul
set HTTPS_PROXY=http://127.0.0.1:18080
set HTTP_PROXY=http://127.0.0.1:18080
"D:\Python\Python310\python.exe" "%~dp0app.py"
pause
