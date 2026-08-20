#!/bin/bash
set -e

# Make sure we are at the project root
cd "$(dirname "$0")/.."

echo "=================================================="
echo "STEP 1: Downloading & Extracting High-Res Keyframes (L21 to L26_b)"
echo "=================================================="
PYTHONPATH=mvp-app mvp-app/.venv/bin/python tools/download_and_extract_keyframes.py

echo "=================================================="
echo "STEP 2: Running Vintern-1B OCR Extraction"
echo "=================================================="
PYTHONPATH=mvp-app mvp-app/.venv/bin/python system1/research/ocr_asr/ocr/extract_ocr_vintern.py

echo "=================================================="
echo "Pipeline execution completed successfully!"
echo "=================================================="
