# Storage Strategy

## Status

Canonical. Storage follows the app-ready contract in `docs/architecture/data-contracts.md`.

## Roots

| Root | Contents | Performance Target |
| --- | --- | --- |
| `${REPO_ROOT}` | Code, docs, schemas, config, tiny fixtures | Small and git-safe. |
| `${AIC_DATA_ROOT}` | Raw videos/keyframes, processed media, DuckDB warehouse, preprocessing reports | Large external storage, usually HDD. |
| `${AIC_RUNTIME_ROOT}` | `app.sqlite`, WAL/SHM files, FTS5 tables, FAISS indexes, small runtime cache | Hot storage, preferably SSD. |

Do not store real competition media in the repository. Any earlier `data/` examples are logical artifact trees, not physical repo layout.

## Source Of Truth

| Data Type | Runtime Source Of Truth |
| --- | --- |
| Catalog, IDs, evidence metadata, sessions, candidates, agent traces | SQLite WAL at `${AIC_RUNTIME_ROOT}/db/app.sqlite` |
| Text search | SQLite FTS5 tables inside `app.sqlite` |
| Visual vectors | FAISS files under `${AIC_RUNTIME_ROOT}/indexes/` |
| Vector-to-keyframe mapping | SQLite `vector_map` |
| Videos/keyframes/thumbnails | `video_ref`, `keyframe_ref`, and `thumbnail_ref` in SQLite, resolved through `MediaStorePort` |
| Raw JSON/CSV/Parquet | Input, staging, debug, or validation only |
| DuckDB | Offline preprocessing, staging, analytics, and validation only |

## Media Resolution

SQLite stores canonical logical refs such as:

```text
raw_videos/{video_id}.mp4
keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
```

`video_ref` is the canonical raw-video logical ref. `keyframe_ref` and
`thumbnail_ref` are the canonical logical refs for generated images. Use a
generic `media_ref` field only in adapter-style tables that genuinely need one
abstract media column.

The backend resolves those refs through `MediaStorePort`. MVP uses `LocalFileMediaStore`; MinIO can be added later behind the same port.

## Operational Rules

- Never persist absolute machine paths in SQLite.
- Keep FAISS manifests beside FAISS index files.
- Keep cache disposable; cache invalidation is tied to `dataset_id` and index manifest versions.
- Treat app-ready validation failure as a blocker for runtime startup.
