# Phase 0 — Canonical Foundation

## Status

Completed in docs. Keep as historical implementation foundation.

## Maps To

- `MVP-0`
- `MVP-0.5`

## Goal

Chốt source of truth trước khi viết runtime code:

- product vocabulary;
- architecture boundaries;
- app-ready data contract;
- storage strategy;
- ingestion/runtime split;
- canonical IDs and media refs;
- backlog and test matrix.

## Why This Phase Exists

Nếu không có phase này, team sẽ build backend/UI/search trên giả định mơ hồ:

- ID không thống nhất;
- path lưu media không thống nhất;
- không rõ raw data khác gì app-ready data;
- không rõ runtime dùng SQLite/FTS5/FAISS ra sao;
- không rõ query/result payload shape.

## Delivered Outputs

- canonical docs trong `docs/architecture/`
- canonical docs trong `docs/product/`
- ADRs liên quan data contract và IDs
- archived source inputs
- synced `docs/validation/test-matrix.md`
- synced `harness.db`

## Exit Criteria

Phase được xem là xong khi:

1. Canonical docs không còn conflict lớn.
2. `MVP-0` và `MVP-0.5` là implemented trong matrix.
3. Team có thể đọc docs canonical mà không cần dựa vào source input cũ.
4. Có thể bắt đầu thiết kế `MVP-0.6` mà không cần đoán contract dữ liệu.

## Risks Closed By This Phase

- lệch vocabulary giữa docs và code tương lai;
- sai format `keyframe_id`;
- nhầm raw paths thành runtime source of truth;
- build retrieval trước khi có mapping contract.

## Evidence

- `docs/architecture/data-contracts.md`
- `docs/architecture/system1-ingestion.md`
- `docs/architecture/system2-retrieval.md`
- `docs/validation/test-matrix.md`
