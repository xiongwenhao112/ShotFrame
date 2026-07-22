@echo off
rem ShotFrame 打包脚本：生成 dist\ShotFrame.exe
cd /d "%~dp0"
python make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name ShotFrame ^
  --icon assets\icon.ico ^
  --add-data "assets\icon.ico;assets" ^
  --collect-all tkinterdnd2 ^
  main.py
echo.
echo 打包完成: dist\ShotFrame.exe
pause
