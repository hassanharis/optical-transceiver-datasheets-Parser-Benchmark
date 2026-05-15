#!/usr/bin/env bash
set -euo pipefail

echo "=== Optical Transceiver Datasheet Parser Benchmark ==="

if [ ! -d "venv" ]; then
  python -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m parsers.run_opendataloader
python -m parsers.run_opendataloader_hybrid
python -m parsers.run_docling
python -m parsers.run_marker
python -m parsers.run_pymupdf4llm
python -m parsers.run_unstructured_fast
python -m parsers.run_unstructured_hires

python -m evaluation.evaluate_tables
python -m evaluation.evaluate_structure
python -m evaluation.aggregate_scores

echo "=== Done. See reports/summary.csv and reports/observability/events.jsonl ==="
