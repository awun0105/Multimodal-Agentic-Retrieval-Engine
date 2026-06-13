# Phase 5 — Keyframe-first UI Vertical Slice

## Maps To

- `MVP-3`
- `SYS2-002`

## Goal

Dựng UI đầu tiên chạy trên API thật của System 2:

- result grid
- keyframe detail
- nearby keyframes
- copy `video_id/frame_id`

## Scope

- SPA shell
- result/detail panel
- nearby strip
- loading/error states
- copy actions

## Suggested Issue Breakdown

1. Bootstrap UI shell
2. Render keyframe detail from API
3. Render nearby keyframes
4. Add copy actions
5. Add loading/error states

## Done Criteria

1. User xem được keyframe-first workflow cơ bản.
2. UI chạy trên payload thật, không phải mock.
3. Team có vertical slice browser đầu tiên.

## Validation

- manual browser checks
- payload rendering checks
- copy action checks

## Risks

- UI invents fields not in API;
- browser flow không phản ánh data model thật.
