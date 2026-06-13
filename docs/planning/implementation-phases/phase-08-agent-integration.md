# Phase 8 — Agent Integration

## Maps To

- `MVP-9`
- `SYS2-005`

## Goal

Thêm agent như một lớp automation dùng chung retrieval core, cùng APIs, cùng result model với UI.

## Scope

- agent tool adapter
- agent run persistence
- agent steps trace
- UI agent panel
- accept/edit/reject flow

## Suggested Issue Breakdown

1. Define agent tool interface
2. Persist agent runs/steps
3. Build agent UI panel
4. Add human override flow
5. Add runtime guards

## Done Criteria

1. Agent dùng cùng retrieval/evidence APIs với UI.
2. Agent output traceable.
3. Human vẫn kiểm soát kết quả cuối.

## Validation

- simulated agent runs
- trace review
- session/candidate consistency checks

## Risks

- agent bypasses runtime contracts;
- trace không đủ mạnh để debug.
