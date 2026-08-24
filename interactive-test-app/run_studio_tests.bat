@echo off
chcp 65001 > nul
echo ========================================================================
echo  [AIC 2026] KIEM TRA RUNTIME & CAU TRUC 3 TANG INTERACTIVE STUDIO
echo ========================================================================
echo.

echo [BUOC 1/2] Dang chay kiem tra toan ven kien truc test_studio_structure.py...
python interactive-test-app/test_studio_structure.py
if %errorlevel% neq 0 (
    echo.
    echo [THAT BAI] Kiem tra cau truc kien truc phat hien loi!
    pause
    exit /b %errorlevel%
)
echo.

echo [BUOC 2/2] Dang chay kiem tra Runtime E2E test_step7_interactive_app_e2e.py...
python system1-kaggle-pipeline/scripts/steps/test_step7_interactive_app_e2e.py
if %errorlevel% neq 0 (
    echo.
    echo [THAT BAI] Kiem tra Runtime E2E phat hien loi!
    pause
    exit /b %errorlevel%
)
echo.

echo ========================================================================
echo   [THANH CONG] INTERACTIVE COCKPIT STUDIO DAT 100%% ALL PASS!
echo ========================================================================
echo.
pause
