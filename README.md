# Optical Datasheet Parser Benchmark

Benchmark harness for evaluating PDF parsing quality on optical transceiver datasheets.

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

## Outputs

- Ranked summary: `reports/summary.csv`
- Workflow observability events: `reports/observability/events.jsonl`
- Per-parser scores: `outputs/{parser}/scores/{pdf_stem}.json`

## Interpreting Scores

- `TCA` measures per-cell similarity against ground truth tables.
- `FLS` measures whether footnote anchors and bodies are preserved and linked.
- `SS` measures heading recall, table count accuracy, and table order alignment.
- `MMNS` measures correct separation of modulation blocks (QPSK/8-QAM/16-QAM).
- `composite = 0.40*TCA + 0.25*FLS + 0.20*SS + 0.15*MMNS`
- Tier-weighted aggregation prioritizes harder PDFs.

If `corpus/ground_truth` is empty, quality scores cannot be computed and `summary.csv` will only include available headers.
