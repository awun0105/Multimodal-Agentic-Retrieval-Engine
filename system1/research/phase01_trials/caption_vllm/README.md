# Caption throughput trial: vLLM

Step 5b item 3 of `docs/plans/active/system1-pipeline-simplification.md`.

Tests whether vLLM 0.11.0 with structured outputs (JSON schema `CAPTION_SCHEMA`)
captions shots faster than the current transformers `generate` + xgrammar path
on one Kaggle T4, at the same prompt, schema, image size (512), token limit
(700), and batch size (16, as `max_num_seqs`). Validity uses `parse_caption`.

Baseline (transformers, T4): 3.43 s/shot, valid JSON 98.3%; `L23_V010` 231 s
for 93 shots, `L23_V004` 297 s for 107 shots.

## Run

```bash
cd system1/research/phase01_trials/caption_vllm
kaggle kernels push -p .
```

In the Kaggle editor for `quanlam/mare-caption-vllm`: set accelerator GPU T4 x2,
attach the `HF_TOKEN` secret (read access to `1thesudden/AIOU26_release_test`),
then Save & Run All. Output: `/kaggle/working/caption_vllm_report.json`.

vLLM is installed alone; it is not tested beside `system1[worker]`. If vLLM
wins, a second check is needed that it installs beside the worker models.

## Record in the plan (Progress, Step 5b item 3)

Commit, vLLM version, model load seconds, per-video seconds and shots,
seconds/shot, valid JSON count and rate, problems histogram, and whether the
first 3 captions read the same as transformers output. Decision: keep the
faster path only if valid rate is not lower than 98.3%.
