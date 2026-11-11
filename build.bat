@echo off
chcp 65001 >nul
"D:\Python\Python310\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name "dota-stats" --distpath "%~dp0dist-py" --workpath "%~dp0build-py" --specpath "%~dp0" "%~dp0app.py"
if errorlevel 1 goto :fail
copy /y "%~dp0dist-py\dota-stats.exe" "%~dp0dota-stats.exe" >nul
echo.
echo Build done: dota-stats.exe
pause
exit /b 0
:fail
echo.
echo Build failed.
pause
exit /b 1
