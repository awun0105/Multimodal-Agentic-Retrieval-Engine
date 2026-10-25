# Phase 4 — System 2 Runtime Data And API Backbone

## Maps To

- `MVP-2`
- `SYS2-001`

## Goal

Dựng xương sống runtime của System 2 trên app-ready artifacts thật từ System 1:

- repository layer
- dataset health
- keyframe detail
- evidence detail
- nearby keyframes
- media resolution

## Main Question This Phase Answers

"System 2 đã đọc được app-ready artifacts thật và expose được canonical API payload chưa?"

## Scope

### A. Repository/runtime read layer

- load SQLite
- resolve logical refs
- fetch keyframe/evidence records

### B. FastAPI vertical slice

- `GET /api/health`
- `GET /api/datasets/current`
- `GET /api/datasets/current/health`
- `GET /api/keyframes/{keyframe_id}`
- `GET /api/keyframes/{keyframe_id}/evidence`
- `GET /api/videos/{video_id}/keyframes?...`

## Suggested Issue Breakdown

1. Implement runtime config loading
2. Implement repository read methods
3. Implement media resolver
4. Add dataset health endpoint
5. Add keyframe detail endpoint
6. Add evidence endpoint
7. Add nearby keyframes endpoint

## Done Criteria

1. System 2 đọc được data-ready thật từ System 1.
2. API trả đúng payload canonical.
3. UI có thể dùng payload này trực tiếp ở phase sau.

## Validation

- API tests on real artifacts
- manual query by keyframe_id/video_id
- payload review against product API docs

## Risks

- System 2 assumptions lệch artifact thật;
- media resolution sai do path handling;
- payload chưa đủ cho UI.
