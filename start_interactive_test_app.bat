@echo off
chcp 65001 >nul
title AIC 2026 Interactive Cockpit Studio
cd /d "%~dp0"

echo ========================================================================
echo   KHOI CHAY RETRIEVAL COCKPIT STUDIO (AIC 2026)
echo ========================================================================
echo.
echo [1/2] Dang kiem tra moi truong va giai phong cong mang...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":7860" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/2] Dang khoi chay Web Studio tai http://127.0.0.1:7860 ...
echo (Trinh duyet web se tu dong mo len trong giay lat)
echo.
python "interactive-test-app\app.py"

if %errorlevel% neq 0 (
    echo.
    echo ========================================================================
    echo   [LOI] Khong the khoi chay Web Studio.
    echo   Vui long kiem tra da cai dat cac goi thu vien: pip install gradio opencv-python ultralytics pandas
    echo ========================================================================
    pause
)
