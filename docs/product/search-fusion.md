# Search Fusion

## Status

Canonical minimum scoring model. Exact weights are configurable, but result payload shape and score semantics must stay stable.

## Score Components

Every search result may include these normalized components:

| Component | Source |
| --- | --- |
| `visual` | FAISS visual/image embeddings. |
| `caption` | Caption FTS5 or caption embedding adapter. |
| `ocr` | OCR FTS5. |
| `asr` | ASR transcript FTS5/time evidence. |
| `object` | Object/concept FTS5 or structured filters; text source rows use `source_type = object_labels`. |
| `metadata` | Title, source/channel, tags, annotations. |
| `rerank` | Optional top-K reranker output. |

Missing modalities score `0` and should be visible as missing evidence, not treated as validation failure.

## Default Weights

| Query Type | visual | caption | ocr | asr | object | metadata |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `tkis` | 0.25 | 0.25 | 0.15 | 0.15 | 0.15 | 0.05 |
| `qa` | 0.15 | 0.25 | 0.20 | 0.20 | 0.15 | 0.05 |
| `trake` | 0.20 | 0.15 | 0.10 | 0.10 | 0.15 | 0.30 |
| `vkis` | 0.45 | 0.20 | 0.05 | 0.05 | 0.20 | 0.05 |

Weights are starting defaults, not competition truth. They must be config-driven.

## Fusion Algorithm

1. Run available retrieval adapters.
2. Normalize each adapter score to `[0, 1]`.
3. Merge hits by `keyframe_id`.
4. Compute weighted sum from available components.
5. Retain raw per-modality rank and evidence snippets.
6. Apply optional same-video diversification.
7. Rerank top-K with richer evidence when enabled.
8. Return final score, score components, evidence, and warnings.

## Diversification

When `group_by_video=true`, avoid returning only near-duplicate frames from one video. The UI must allow users to turn this off for TRAKE and same-video exploration.

## Evidence Summary Shape

```json
{
  "score": 0.87,
  "score_components": {
    "visual": 0.91,
    "caption": 0.72,
    "ocr": 0.0,
    "asr": 0.44,
    "object": 0.66,
    "metadata": 0.15,
    "rerank": null
  },
  "evidence": [
    {"type": "caption", "text": "short snippet", "score": 0.72, "source": "caption_fts"}
  ],
  "warnings": ["ocr_missing"]
}
```
