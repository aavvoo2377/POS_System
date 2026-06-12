@echo off
chcp 65001 >nul
cd /d "%~dp0"
py main.py
if %errorlevel% neq 0 (
    py -m pip install -r requirements.txt
    pause
)
