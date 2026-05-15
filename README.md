# Optical Datasheet Parser Benchmark

Benchmark harness for evaluating PDF parsing quality on optical transceiver datasheets.

## Benchmark Result: Reviewed Datasheet Subset

This repository includes a reproducible benchmark slice intended for reporting parser quality on optical transceiver datasheets. The evaluated subset contains 9 fully reviewed, non-empty ground-truth datasheets from `corpus/ground_truth`; 3 zero-table Nokia datasheets are excluded from this result set.

The benchmark compares 7 parser output types using the repository KPI definitions:

- `TCA`: Table Cell Accuracy
- `FLS`: Footnote Linkage Score
- `SS`: Structure Score
- `MMNS`: Multi-modulation Normalization Score
- `Composite`: `0.40*TCA + 0.25*FLS + 0.20*SS + 0.15*MMNS`

`FLS` and `MMNS` are scored only where applicable, then the composite is reweighted over the available KPI components. The table below reports tier-weighted scores for the reviewed subset.

| Rank | Parser | Composite | TCA | FLS | SS | MMNS | Speed score | Seconds/page |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `docling` | 0.8270 | 0.8521 | 0.7284 | 0.8983 | 0.6500 | 0.6977 | 1.7698 |
| 2 | `unstructured_hires` | 0.8170 | 0.8485 | 0.7284 | 0.8499 | 0.6500 | 0.6751 | 2.2242 |
| 3 | `marker` | 0.7658 | 0.8080 | 0.5972 | 0.8336 | 0.6500 | 0.5691 | 7.0003 |
| 4 | `pymupdf4llm` | 0.6652 | 0.6681 | 0.4486 | 0.8200 | 0.8500 | 0.8455 | 0.5409 |
| 5 | `unstructured_fast` | 0.1873 | 0.0000 | 0.2539 | 0.4000 | 0.9000 | 0.9535 | 0.1353 |
| 6 | `opendataloader_heuristic` | 0.0637 | 0.0000 | 0.0000 | 0.2346 | 0.0000 | 1.0000 | 0.0000 |
| 7 | `opendataloader_hybrid` | 0.0637 | 0.0000 | 0.0000 | 0.2346 | 0.0000 | 1.0000 | 0.0000 |

In this reviewed subset, `docling` achieves the highest overall composite score (`0.8270`), closely followed by `unstructured_hires` (`0.8170`). `pymupdf4llm` is the fastest high-quality parser and has the strongest `MMNS` score, while `marker` provides competitive extraction quality at higher runtime. The OpenDataLoader runs produced `library not installed` outputs in this environment, so their scores should be interpreted as failed-run baselines rather than final parser capability measurements.

For a detailed result narrative, reviewed-file list, and reproduction notes, see `REVIEWED_DATASHEET_KPI_FINDINGS.md`.

## What This Runs

- 7 parsers:
  - `opendataloader_heuristic`
  - `opendataloader_hybrid`
  - `docling`
  - `marker`
  - `pymupdf4llm`
  - `unstructured_fast`
  - `unstructured_hires`
- Evaluation metrics:
  - Table Cell Accuracy (TCA)
  - Footnote Linkage Score (FLS)
  - Structure Score (SS)
  - Multi-modulation Normalization Score (MMNS)
  - Composite weighted by complexity tier
- Observability:
  - End-to-end workflow events in `reports/observability/events.jsonl`

## Install

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Linux/macOS

```bash
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Data Layout

- Input PDFs are read from `datasheets/` (configured in `config.yaml`).
- Ground truth JSON files go in `corpus/ground_truth/`.
- Parser outputs go in `outputs/{parser}/` as both `.md` and `.json`.

## Add a New PDF

1. Place the PDF in `datasheets/`.
2. Create `corpus/ground_truth/{pdf_stem}.json`.
3. Follow schema in `optical_datasheet_parser_benchmark_spec.md` section 5.
4. Ensure required fields exist:
   - root: `source`, `tier`, `tables`, `structure`
   - each table: `table_id`, `headers`, `rows`

## Review Ground Truth Tables

Launch a local browser editor for the JSON files in `corpus/ground_truth/`:

```powershell
.\venv\Scripts\python.exe ground_truth_table_editor.py
```

The editor lets you choose a ground-truth JSON, edit table metadata, headers, cells, rows, columns, footnotes, and structure JSON. Saves update the selected JSON file and create a timestamped `.bak` backup next to it.

## Run Full Benchmark

### Windows

```powershell
./run_all.ps1
```

### Linux/macOS

```bash
bash run_all.sh
```

## Run Individual Stages

```powershell
.\venv\Scripts\python.exe parsers/run_docling.py
.\venv\Scripts\python.exe evaluation/evaluate_tables.py
.\venv\Scripts\python.exe evaluation/evaluate_structure.py
.\venv\Scripts\python.exe evaluation/aggregate_scores.py
```

## Reproduce Reviewed-Subset Results

```powershell
python evaluation\llm_rescore_reviewed.py
```

This writes:

- `reports/llm_rescore_reviewed_summary.csv`
- `reports/llm_rescore_reviewed_detail.csv`
- `reports/llm_rescore_reviewed.json`

## Outputs

- Ranked summary: `reports/summary.csv`
- Workflow observability events: `reports/observability/events.jsonl`
- Per-parser scores: `outputs/{parser}/scores/{pdf_stem}.json`
- Reviewed-subset KPI findings: `REVIEWED_DATASHEET_KPI_FINDINGS.md`
- Reviewed-subset generated reports: `reports/llm_rescore_reviewed_*`

## Interpreting Scores

- `TCA` measures per-cell similarity against ground truth tables.
- `FLS` measures whether footnote anchors and bodies are preserved and linked.
- `SS` measures heading recall, table count accuracy, and table order alignment.
- `MMNS` measures correct separation of modulation blocks (QPSK/8-QAM/16-QAM).
- `composite = 0.40*TCA + 0.25*FLS + 0.20*SS + 0.15*MMNS`
- Tier-weighted aggregation prioritizes harder PDFs.

If `corpus/ground_truth` is empty, quality scores cannot be computed and `summary.csv` will only include available headers.
