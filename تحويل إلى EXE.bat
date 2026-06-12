@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install pyinstaller
py build_exe.py
pause