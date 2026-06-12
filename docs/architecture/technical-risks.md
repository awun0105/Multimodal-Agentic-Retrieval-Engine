# Technical Risks

## Status

Canonical Technical Risks tracking. Derived from `SPEC.md`.

## Risk 1: Dataset Format Uncertainty

- **Risk**: 2026 organizers change the dataset format (e.g., no keyframes, new metadata format).
- **Mitigation**: System 1 ingestion notebooks are decoupled. Adapters must be written for the exact format once released. System 2 is shielded from raw layout.

## Risk 2: RAM Exhaustion

- **Risk**: A massive 2026 dataset may produce a FAISS index too large for RAM, or the UI may load too many high-res images.
- **Mitigation**:
  - Use WebP 160px/320px thumbnails for grids.
  - Implement virtualized lists in React.
  - Support memory-mapped FAISS indices if needed.
  - SQLite metadata is queried on-demand.

## Risk 3: HDD Bottleneck

- **Risk**: Raw videos or massive image folders on an external HDD cause slow IO during search.
- **Mitigation**: Live search only reads SQLite, FAISS, and SSD-cached thumbnails. Raw video files are only touched for on-demand playback/preview.

## Risk 4: Agent Latency and Unpredictability

- **Risk**: Agent loops burn too much time or drift from the objective.
- **Mitigation**:
  - Agent must use the same fast retrieval APIs as humans.
  - Strictly enforce `max_steps` and `max_runtime_sec`.
  - Provide an easy human-override interrupt.

## Risk 5: Submission Format Changes

- **Risk**: 2026 requires an active REST API submission or a very different CSV.
- **Mitigation**: Export behavior is a configurable output helper, not a core retrieval engine dependency.
