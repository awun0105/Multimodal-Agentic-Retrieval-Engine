# Phase 7 — Hybrid Search, Workspace, And Submission

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
- submission helper

## Scope

- hybrid endpoint
- fusion and rerank service
- query session persistence
- candidate basket backend/UI
- answer draft, review, submission history, and configurable organizer API adapter

## Suggested Issue Breakdown

1. Implement hybrid endpoint
2. Add score fusion service
3. Add session persistence
4. Add clue handling
5. Add candidate basket
6. Add submission helper

## Done Criteria

1. Người dùng có thể search và giữ trạng thái làm việc.
2. Có thể lưu candidate, tạo answer draft, review/edit, và xem submission history.
3. Workflow TKIS/Q&A/TRAKE/VKIS có baseline usable.

## Validation

- manual workflow checks
- session persistence tests
- candidate/submission checks

## Risks

- overfit submission helper theo rule/API chưa chốt;
- workspace state lệch canonical query model.
