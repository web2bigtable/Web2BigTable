# Revision induction datasets

This directory contains the frozen offline skill-induction records used in
the Web2BigTable revision.

## WideSeek-R1 selection

- `wideseek_r1_external20.jsonl`: 20 high-search-volume records selected
  from the public WideSeek-R1 training dataset.
- `wideseek_r1_external20.manifest.json`: pinned source revisions,
  selection rules, record identifiers, and contamination-audit summary.

The source dataset is available from
<https://huggingface.co/datasets/RLinf/WideSeek-R1-train-data> under its
stated Apache-2.0 licence.

## Adapted XBench selection

- `xbench_adapted20.jsonl`: 20 manually adapted Chinese training questions
  with unique IDs 901--920. Each record contains a prompt, reference answer,
  reference reasoning steps, and an unused baseline field.

These records are used only during offline skill induction. They are disjoint
from the unmodified XBench-DeepSearch evaluation instances. The orchestrator
and worker skill banks are frozen before evaluation.

## Evaluation separation

WideSearch, XBench-DeepSearch, and DeepWideSearch evaluation records are not
included in this directory and are referenced through their official
benchmark repositories.
