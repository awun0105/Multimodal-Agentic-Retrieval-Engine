# Phase 7 — Hybrid Search, Workspace, And Output

## Maps To

- `MVP-6`
- `MVP-7`
- `MVP-8`

## Goal

Hoàn thiện workflow làm việc thật của người dùng:

- hybrid fusion
- query sessions
- clues/notes/history
- candidate basket
- output helper

## Scope

- hybrid endpoint
- fusion and rerank service
- query session persistence
- candidate basket backend/UI
- output helper

## Suggested Issue Breakdown

1. Implement hybrid endpoint
2. Add score fusion service
3. Add session persistence
4. Add clue handling
5. Add candidate basket
6. Add output helper

## Done Criteria

1. Người dùng có thể search và giữ trạng thái làm việc.
2. Có thể lưu candidate và export output cơ bản.
3. Workflow TKIS/Q&A/TRAKE/VKIS có baseline usable.

## Validation

- manual workflow checks
- session persistence tests
- candidate/export checks

## Risks

- overfit output helper theo rule chưa chốt;
- workspace state lệch canonical query model.
