@echo off
python -m PyInstaller --noconfirm --onefile --windowed --name "dota-stats" --distpath "%~dp0dist-py" --workpath "%~dp0build-py" --specpath "%~dp0" "%~dp0app.py"
copy /y "%~dp0dist-py\dota-stats.exe" "%~dp0dota-stats.exe" >nul
echo.
echo Build done: dota-stats.exe
pause
