# HUONG DAN SU DUNG: INTERACTIVE RETRIEVAL COCKPIT & BENCHMARK STUDIO (AIC 2026)

Ung dung Visual Cockpit & Studio doi chieu thuc nghiem duoc thiet ke theo tieu chuan tuong tac VBS / LSC phuc vu cuoc thi AI Challenge 2026.

---

## 1. Ban Do 5 Tab Tinh Nang Chinh

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                   INTERACTIVE MULTIMODAL RETRIEVAL COCKPIT (GIAO DIEN 5 TINH NANG)                     │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 1: SO SANH TRUC QUAN SIDE-BY-SIDE (BTC vs. SYSTEM 1 TU XU LY)                                      │
│   - Nua Trai: Keyframe Ban To Chuc (BTC) + The [BTC-xu ly] khi mat do thong tin thap.                   │
│   - O Giua: Dong Thoi Gian Truc Quan (Timeline Tracker) + Nut Bam "Xem YouTube (mm:ss)".               │
│   - Nua Phai: Keyframe System 1 + He Thong Da Nhan (Multi-Badge: Frame Cat Nghia, Da Lam Net, Tieu De).│
│   - Cu Phap Nop Bai Tu Dong: Tu sinh ma video_id,frame_idx cho moi khung hinh.                         │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 2: TRINH QUAN LY & LUU TRU KET QUA (PERSISTENCE & MEMORY-SAVING HUB)                               │
│   - Bang thong ke tong hop tat ca video da xu ly, so luong shot, do net trung binh va dung luong WebP. │
│   - Xuat du lieu linh hoat sang JSON va CSV hop nhat phuc vu cham thi.                                 │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 3: KHAM PHA STEP 1-5 (BENCHMARK STEP HARNESS)                                                      │
│   - Kiem tra doc lap: Genre Classifier, Video QA ASR Timestamp Search, OCR Chan Trang, Frame Cat Nghia.│
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 4: TIM KIEM TRUC QUAN KIS & VIDEO QA (SYSTEM 2 HYBRID SEARCH)                                      │
│   - Tim kiem da phuong thuc lai: Dense Vector Search (SigLIP) + Sparse FTS5 BM25 + ASR Audio QA.       │
│   - Khuu trung lap khung hinh (Temporal Deduplication) va RRF Rank Fusion.                             │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ TAB 5: STUDIO TUY CHINH THAM SO DAU VAO (SYSTEM 1 PARAMETER TUNING)                                    │
│   - Tuy chinh toan bo tham so: Video nguon, Dai frame quet, Nguong Histogram, Loc do net Laplacian.   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cach Khoi Dong Ung Dung

### Cach 1: 1-Click Bang File Batch (Khuyen Dung)
Nhap dup chuot vao tep:
[start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat)

### Cach 2: Chay Bang Terminal / PowerShell
```powershell
python interactive-test-app/launcher.py
```

Truy cap tren trinh duyet web: **`http://127.0.0.1:7860`**

---

## 3. Tai Lieu Tham Chieu Chuyen Sau

- [Tong Quan Kien Truc He Thong (Architecture Overview)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/SYSTEM_ARCHITECTURE_AND_PIPELINE_OVERVIEW.md)
- [Cam Nang Huong Dan Van Hanh & Thu Tu Xu Ly (Run & Execution Guide)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/RUN_AND_EXECUTION_GUIDE_README.md)
- [So Tay Phong Ngua Loi & Du Lieu Bien (Error Prevention & Edge Cases)](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/ERROR_PREVENTION_AND_EDGE_CASES_README.md)
