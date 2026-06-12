@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Building LicenseGenerator.exe...

set APP_NAME=LicenseGenerator
set MAIN_SCRIPT=license_gui.py

if exist "build_license" rmdir /s /q "build_license"
if exist "dist_license" rmdir /s /q "dist_license"
if exist "%APP_NAME%.spec" del "%APP_NAME%.spec"

py -m PyInstaller --onefile --windowed ^
    --name "%APP_NAME%" ^
    --distpath dist_license ^
    --workpath build_license ^
    --hidden-import license_utils ^
    "%MAIN_SCRIPT%"

if %errorlevel% neq 0 (
    echo FAILED!
    pause
    exit /b 1
)

if exist "dist_license\%APP_NAME%.exe" (
    echo SUCCESS: dist_license/%APP_NAME%.exe
)

pause
