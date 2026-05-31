# Data Flow

## End-To-End Flow

```text
official data
  -> ingest/register
  -> generate thumbnails/keyframes/previews
  -> normalize metadata/objects/OCR/ASR/captions
  -> build DB and indexes
  -> search
  -> inspect
  -> save candidate
  -> validate/export
```

## Ingestion Inputs

The official dataset may contain some or all of:

- raw videos;
- keyframes;
- CLIP embeddings;
- object JSON files;
- metadata;
- OCR/transcripts/captions.

The importer should accept whatever is provided and skip missing parts cleanly.

## Generated Artifacts

```text
processed/thumbs/       small WebP/JPEG for result grid
processed/keyframes/    medium images for inspection/search
processed/previews/     compressed videos for fast playback, optional
dense_frame_cache/      temporary dense frames around opened clips, optional
indexes/                FAISS and text indexes
app.sqlite              metadata, sessions, candidates
```

Do not generate full video frames for every video by default.

## Search Data Flow

```text
query
  -> parsed query terms
  -> vector search
  -> text/object/OCR/ASR search
  -> result fusion
  -> diversification by video/time
  -> top frame candidates
  -> UI thumbnail grid
```

Search should not read raw video files.

## Automatic Agent Data Flow

```text
query
  -> classify route
  -> parse clues/constraints
  -> call search APIs
  -> call filter/similar/evidence/timeline APIs
  -> rerank candidates
  -> choose candidate rows
  -> validate output shape
  -> return ranked results and trace
```

The agent uses the same APIs as the interactive UI. Its trace must be visible so
humans can inspect why it chose a result.

## Inspection Data Flow

```text
candidate selected
  -> load keyframe
  -> load nearby keyframes/timeline
  -> stream preview/raw video at timestamp
  -> show evidence
  -> user selects final frame
```

Raw video is used only after a candidate is opened.

## Shardable Preprocessing

Heavy preprocessing must be shardable so laptops/Colab/Kaggle can share work:

```text
prepare-shard --shard-id 0 --num-shards 20
prepare-shard --shard-id 1 --num-shards 20
...
merge-shards
validate-artifacts
build-indexes
```

Each shard should output deterministic files plus checksums.

## Validation Data Flow

```text
saved candidates
  -> query-type formatter
  -> CSV writer
  -> zip/package writer
  -> validator
  -> final upload file
```

Validation rules must be configurable until official 2026 rules are known.
