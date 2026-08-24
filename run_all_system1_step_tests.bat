@echo off
chcp 65001 >nul
title AIC 2026 - System 1 All Step Tests Runner (Steps 1 to 6)
cd /d "%~dp0"

echo ========================================================================
echo   AIC 2026: CHUONG TRINH KIEM THU TOAN DIEN SYSTEM 1 (STEPS 1 - 6)
echo ========================================================================
echo.

echo [BUOC 1/6] Dang chay Step 1: Event Keyframes va Quality Filter...
python "system1-kaggle-pipeline\scripts\steps\test_step1_event_keyframes.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 1 that bai!
    goto error_handler
)
echo.

echo [BUOC 2/6] Dang chay Step 2: Video OCR Extraction va Jaccard Dedup...
python "system1-kaggle-pipeline\scripts\steps\test_step2_video_ocr_dedup.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 2 that bai!
    goto error_handler
)
echo.

echo [BUOC 3/6] Dang chay Step 3: ASR Speech-to-Text va Sub-2ms Video QA...
python "system1-kaggle-pipeline\scripts\steps\test_step3_asr_timestamp_qa.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 3 that bai!
    goto error_handler
)
echo.

echo [BUOC 4/6] Dang chay Step 4: Metadata-Driven Video Genre Classifier...
python "system1-kaggle-pipeline\scripts\steps\test_step4_genre_classifier.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 4 that bai!
    goto error_handler
)
echo.

echo [BUOC 5/6] Dang chay Step 5: Timeline Merge, BTC Context va Semantic Difference...
python "system1-kaggle-pipeline\scripts\steps\test_step5_timeline_merge_dedup.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 5 that bai!
    goto error_handler
)
echo.

echo [BUOC 6/7] Dang chay Step 6: Vietnamese Cultural Lexicon va Faithful Query Enricher...
python "system1-kaggle-pipeline\scripts\steps\test_step6_cultural_lexicon_and_query.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 6 that bai!
    goto error_handler
)
echo.

echo [BUOC 7/7] Dang chay Step 7: Interactive Cockpit App End-to-End Runtime Test...
python "system1-kaggle-pipeline\scripts\steps\test_step7_interactive_app_e2e.py"
if %errorlevel% neq 0 (
    echo [LOI] Step 7 that bai!
    goto error_handler
)
echo.

echo ========================================================================
echo   [THANH CONG] TOAN BO 7/7 STEP TESTS DEU DAT 100%% CHUAN XAC!
echo ========================================================================
echo.
pause
exit /b 0

:error_handler
echo.
echo ========================================================================
echo   [THAT BAI] Da xay ra loi trong qua trinh kiem thu. Vui long kiem tra log.
echo ========================================================================
echo.
pause
exit /b 1
