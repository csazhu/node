@echo off
chcp 65001 >nul
rem 代理已写入 config.json 的 proxy，直接双击 dota-stats.exe 即可，无需在此设环境变量
start "" "%~dp0dota-stats.exe"
