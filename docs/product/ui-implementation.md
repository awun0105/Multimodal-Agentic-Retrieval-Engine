# UI Implementation Specification

## Status

Canonical UI Specification. Derived from `UI_IMPLEMENTATION_SPEC.md` and UI sections in `SPEC.md`.

---

## 1. Single Web UI + Multi-session Workflow

The UI is a single shared web application built as a React/Vite Single Page Application.
- **No authentication**: Teammates access the LAN host and work immediately.
- **Collapsible layouts**: Teammates can toggle panels to maximize screen space during active search.

```text
Top Bar: Query Session Selector, system status, active search input
------------------------------------------------------------------
Left Panel:        | Center:                    | Right Panel:
- Session history  | - Search result grid       | - Selected frame detail
- Clues workspace  | - Virtualized lazy loading | - Timeline inspector
- Pinned basket    | - Group-by-video controls  | - Evidence panels
------------------------------------------------------------------
Bottom bar: Configurable export helpers, keyboard cheatsheet
```

---

## 2. Query Workspace & Sessions

Because multiple teammates collaborate on the same host over LAN, workspace state is scoped:
- **Sessions**: Teammates can select or create a Query Session.
- **Scope**: Search queries, clue lists, notes, and Candidate Baskets are stored in SQLite and bound to the active `session_id`.
- **Client Nickname**: Users can set an optional client nickname (saved in localStorage) to label who added candidates or comments, but this does not require login.

---

## 3. Keyframe-first Grid

The results grid must prioritize speed:
- **Lazy loading**: Thumbnails must be lazy loaded and only rendered if visible.
- **Keyframe detail**: Clicking a thumbnail opens the keyframe detail panel on the right.
- **Same Video Explorer**: Detail view must render adjacent keyframes in a scrollable strip to allow rapid chronological inspection without loading raw video.
- **Video player**: Loading and playing the full `.mp4` file is optional and must only load on-demand.

---

## 4. Layout Panels Detailed

### Query Workspace
- Clue list ordered by progressive reveal time.
- User query history table.
- Selected clue subsets selector.
- Notes text-area.

### Search Controls
- Query input.
- Query type selector: KIS, Q&A, TRAKE, VKIS.
- Modality toggles: Visual, Caption, OCR, ASR, Objects, Metadata.
- Strategy weights adjuster.
- Group-by-video switch.

### Results Grid
- Virtualized list rendering only visible result cards.
- Result card elements: WebP thumbnail, video ID, frame ID, timestamp, score, modality score badges, inspect/pin buttons.

### Detail View
- Max 1280px preview image.
- Play video button (loads raw video seeked to timestamp).
- Navigation: browse next/previous keyframe.

### Same Video Explorer
- Chronological strip showing adjacent keyframes ($N$ frames before/after the selected keyframe).
- Timeline scrollbar.

### Evidence Panel
- OCR matches highlighting exact text.
- ASR transcripts text block showing current segment and nearby time window.
- Captions (VI/EN).
- Object list with confidence labels.

### Candidate Basket
- List of saved candidate cards scoped to the active Query Session.
- Edit answer box for Q&A candidates.
- Frame sequence editor for TRAKE candidates.
- Pin/unpin actions.

### Output Helper
- Simple text area showing copied rows formatted dynamically.
- Configurable CSV download helper.

---

## 5. Browser Memory Strategy

- Render only visible result cards using virtualization.
- Prefer WebP thumbnail URLs over raw base64 data.
- Clear stale search images from browser memory before starting a new query.
- Collapse heavy panels by default.

---

## 6. Keyboard Shortcuts

Fast manual execution must be supported through globally registered key handlers:

| Key | Action |
| --- | --- |
| `/` | Focus search input |
| `Enter` | Run current search |
| `j` / `k` | Move selection to next/previous candidate card |
| `o` | Open detailed inspector for selected card |
| `p` | Pin selected candidate to basket |
| `s` | Save candidate card to runtime persistence |
| `e` | Open export/copy helper pane |
| `Esc` | Close modal or detailed inspector panel |
