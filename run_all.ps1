$ErrorActionPreference = "Stop"

Write-Host "=== Optical Transceiver Datasheet Parser Benchmark ==="

if (-not (Test-Path "venv")) {
    python -m venv venv
}

& .\venv\Scripts\python.exe -m pip install --upgrade pip
& .\venv\Scripts\python.exe -m pip install -r requirements.txt

& .\venv\Scripts\python.exe -m parsers.run_opendataloader
& .\venv\Scripts\python.exe -m parsers.run_opendataloader_hybrid
& .\venv\Scripts\python.exe -m parsers.run_docling
& .\venv\Scripts\python.exe -m parsers.run_marker
& .\venv\Scripts\python.exe -m parsers.run_pymupdf4llm
& .\venv\Scripts\python.exe -m parsers.run_unstructured_fast
& .\venv\Scripts\python.exe -m parsers.run_unstructured_hires

& .\venv\Scripts\python.exe -m evaluation.evaluate_tables
& .\venv\Scripts\python.exe -m evaluation.evaluate_structure
& .\venv\Scripts\python.exe -m evaluation.aggregate_scores

Write-Host "=== Done. See reports/summary.csv and reports/observability/events.jsonl ==="
