# System 1 Notebook Runbook

Operator steps for building a release on Kaggle or Colab. Each batch notebook
holds a settings cell, a setup cell, and one `system1.cli` call. Edit only the
settings cell, then Run All. Design: `docs/architecture/system1-target.md`.

## Order

| Step | Notebook | Runtime | CLI command |
| --- | --- | --- | --- |
| 0 | `00B_master_ingestion_and_assignment.ipynb` (Colab, Drive) or `00C_master_ingestion_local.ipynb` (local machine) | CPU | Phase00 commands; writes batch manifests |
| 1 | `01_worker_batch.ipynb` | Kaggle GPU T4 x2 or Colab | `worker-batch` |
| 2 | `02_caption_batch.ipynb` | Kaggle GPU T4 x2 or Colab | `caption-batch` |
| 3 | `03_build_release.ipynb` | Kaggle CPU kernel (about 30 GB RAM) or Colab | `build-release` |

Run step 0 once per release. Run steps 1 and 2 once per batch; step 2 for a
batch starts after step 1 for that batch has finished. Run step 3 after every
batch of the release has finished steps 1 and 2.

`01_worker_structure_pipeline.ipynb`, `02_worker_feature_enrichment.ipynb`,
and `03_merge_validate_index_release.ipynb` are the old pipeline. Do not run
them; they are removed in plan Step 6.

## Secrets

Add one secret named `HF_TOKEN` (Kaggle: Add-ons, Secrets; Colab: Secrets).
The token needs write access to the output dataset repo and to the bucket
`1thesudden/aiou-app-storage`. The notebooks read it through `kaggle_secrets`,
`google.colab.userdata`, or the environment, and never print it.

## Settings

Every batch notebook has `REPO_URL`, `REPO_REF` (code branch, default `dev`),
and `RELEASE_ID` (default `canonical_release_v001`).

`01_worker_batch.ipynb`:

- `BATCH_ID`: Phase00 batch, for example `batch_000`.
- `WORKER_ID`: name of this session, for example `worker_000`.
- `OUTPUT_REPO`: `1thesudden/AIOU26_release_test` for trials,
  `1thesudden/AIOU26_release` for production.
- `LIMIT`: `None` for the whole batch, or a number of videos for a trial.

`02_caption_batch.ipynb`: the same settings plus `SOURCE_REPO`, the repo that
holds the worker packages (normally the same as `OUTPUT_REPO`).

`03_build_release.ipynb`:

- `SOURCE_REPO`: repo that holds the worker and caption packages.
- `BUCKET_ID`: `1thesudden/aiou-app-storage`.
- `BUCKET_PREFIX`: `releases_test` for trials, `releases` for production.
- `PUBLISH`: `True` uploads to the bucket; `False` builds locally only, and
  the result is lost when the session ends.

## Run Time

Measured on Kaggle with 5 videos (70.3 min of video), plan
`docs/plans/active/system1-pipeline-simplification.md`, Progress:

| Notebook | Measured | Estimate per batch of 73 videos |
| --- | --- | --- |
| `01_worker_batch` (T4) | 43.4 min, 0.62x video length | about 10.5 GPU hours |
| `02_caption_batch` (T4, transformers) | 3.43 s per shot, 1.23x video length | about 2x the worker time |
| `03_build_release` (CPU) | 312 s for 5 videos, peak RSS 560 MB | not measured for a full release |

A Kaggle session ends after 12 hours. A batch that does not finish in one
session continues in the next one (see Resume).

## Resume

Rerun the same notebook with the same settings. Videos whose package is
already in the output repo are skipped. Failed videos are listed in the report
and are retried on the next run.

`03_build_release.ipynb` with `PUBLISH = True` skips media already uploaded to
the bucket and uploads `READY.json` last, so a rerun completes a partial
release.

Run one `BATCH_ID` per session. Two sessions on the same batch at the same
time do duplicate work; a package uploaded by the other session first counts
as `skipped`.

## Outputs

In `OUTPUT_REPO` (a Hugging Face dataset repo):

```text
{RELEASE_ID}/worker/artifacts/{BATCH_ID}/{video_id}.zip
{RELEASE_ID}/worker/reports/{BATCH_ID}_{WORKER_ID}.json
{RELEASE_ID}/captions/artifacts/{BATCH_ID}/{video_id}.zip
{RELEASE_ID}/captions/reports/{BATCH_ID}_{WORKER_ID}.json
```

`02_caption_batch.ipynb` also writes its report after every video to
`/kaggle/working/caption_report/` (Colab: `/content/caption_report/`).
`03_build_release.ipynb` writes `build_report.json` to
`/kaggle/working/build_release_report/`.

In the bucket `BUCKET_ID`:

```text
{BUCKET_PREFIX}/{RELEASE_ID}/media/...
{BUCKET_PREFIX}/{RELEASE_ID}/db/
{BUCKET_PREFIX}/{RELEASE_ID}/indexes/
{BUCKET_PREFIX}/{RELEASE_ID}/manifest.json
{BUCKET_PREFIX}/{RELEASE_ID}/READY.json
```

A release is complete only when `READY.json` exists.

## Verify a Batch

1. Open `{RELEASE_ID}/phase00_ingestion/manifests/{BATCH_ID}.txt` in the
   Phase00 repo (`1thesudden/AIOU26_release`). It lists one `video_id` per
   line.
2. Open the worker report `{RELEASE_ID}/worker/reports/{BATCH_ID}_{WORKER_ID}.json`.
   `completed` plus `skipped` must equal the manifest count, and `failed` must
   be empty. If `failed` is not empty, rerun the notebook.
3. The number of ZIPs under `{RELEASE_ID}/worker/artifacts/{BATCH_ID}/` must
   equal the manifest count.
4. Repeat steps 2 and 3 for `captions/reports/` and `captions/artifacts/`.
5. For a release: `READY.json` exists in the bucket, and the counts in
   `build_report.json` match the number of worker packages.
