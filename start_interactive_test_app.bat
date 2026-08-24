@echo off
chcp 65001 >nul
title AIC 2026 Interactive Cockpit Studio Launcher
cd /d "%~dp0"

echo ========================================================================
echo   KHOI CHAY TRINH DIEU KHIEN RETRIEVAL COCKPIT STUDIO (AIC 2026)
echo ========================================================================
python "interactive-test-app\launcher.py"

if %errorlevel% neq 0 (
    echo.
    echo [LOI] Khong the khoi chay launcher. Vui long kiem tra moi truong Python.
    pause
)
