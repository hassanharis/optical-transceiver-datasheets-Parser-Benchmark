# Optical Transceiver Datasheet Parser Benchmark
## Experiment Specification for Cursor

**Domain:** Optical networking datasheets (Nokia, Ericsson, Cisco, Juniper, Smartoptics)  
**Modules of interest:** QPSK, OpenZR+, OpenROADM, 400ZR, CFP2, QSFP-DD coherent  
**Parsers under test:** OpenDataLoader (heuristic + hybrid), Docling, Marker, PyMuPDF4LLM, Unstructured (fast + hi_res)

---

## 1. Background & Motivation

Optical transceiver datasheets from telecom vendors are among the most hostile PDF layouts for automated extraction:

- **Multi-level merged-cell tables** — e.g., optical specs split across QPSK / 8-QAM / 16-QAM columns with shared row headers
- **Conditional footnotes** — superscript symbols (¹ ² ³ *) that modify numerical limits (e.g., "Min TX power –10 dBm ¹" where ¹ = "measured at OMA")
- **Parameter tables with units in headers** — "Tx Output Power (dBm)" applies to every cell in the column but is never repeated
- **Multi-page spanning tables** — electrical/optical specs that continue across 2–3 pages with repeated headers
- **Mixed-modulation sub-tables** — a single table contains rows for QPSK, 8-QAM, 16-QAM with different row counts per modulation block
- **Application-code tables** — CMIS application codes in tabular form, often with binary hex notation across merged cells
- **Tolerance notations** — values expressed as "–3.0 / +2.5" or "Typ / Min / Max" patterns in a single cell

The downstream goal is a structured knowledge base (JSON/Parquet) for RAG over multi-vendor interoperability data — so **table normalization** and **footnote linkage** are the primary quality axes.

---

## 2. Test Corpus

### 2.1 PDF Sources (collect at least 2–3 per vendor)

| Vendor | Module family | Suggested search |
|--------|--------------|-----------------|
| Cisco | QDD-400G-ZRP-S, QDD-400G-ZR-S | cisco.com transceiver datasheet 400ZR |
| Juniper | JCO400-QDD-ZR-M, JCO100-QDD-ZR | juniper.net pluggable optics datasheet |
| Nokia | UCPE-M-SFP28, coherent QSFP-DD | nokia.com optical networking datasheet |
| Ericsson | MINI-LINK coherent pluggables | ericsson.com product datasheet optical |
| Smartoptics | TQD017-TUNC-SO, TQD011-TUNC-SO | smartoptics.com/wp-content/uploads |
| Lumentum / II-VI / Acacia | (OEM datasheets referenced by above) | publicly available on vendor portals |

### 2.2 Complexity Tiers

Assign each PDF one of three tiers (used later in scoring weights):

- **Tier 1 – Native PDF, simple tables:** Single-header, no footnotes, selectable text
- **Tier 2 – Native PDF, complex tables:** Merged cells, multi-header, footnotes, multi-page span
- **Tier 3 – Scanned / image-heavy PDF:** Optical specs as raster images, vendor logo overlays, mixed OCR

Target: ≥4 Tier-1, ≥4 Tier-2, ≥2 Tier-3 PDFs.

---

## 3. Project Structure

```
optical-parser-bench/
├── README.md
├── requirements.txt
├── corpus/
│   ├── raw/                  # original PDFs
│   │   ├── cisco_400zr.pdf
│   │   ├── juniper_jco400.pdf
│   │   ├── smartoptics_tqd017.pdf
│   │   └── ...
│   └── ground_truth/         # hand-annotated JSON (see §5)
│       ├── cisco_400zr.json
│       └── ...
├── parsers/
│   ├── run_opendataloader.py
│   ├── run_opendataloader_hybrid.py
│   ├── run_docling.py
│   ├── run_marker.py
│   ├── run_pymupdf4llm.py
│   ├── run_unstructured_fast.py
│   └── run_unstructured_hires.py
├── outputs/
│   └── {parser_name}/
│       └── {pdf_stem}.{md|json}
├── evaluation/
│   ├── evaluate_tables.py
│   ├── evaluate_footnotes.py
│   ├── evaluate_structure.py
│   └── aggregate_scores.py
├── reports/
│   └── benchmark_report.html   # auto-generated
└── config.yaml
```

---

## 4. Parser Runner Scripts

### 4.1 `requirements.txt`

```
# Core parsers
opendataloader-pdf>=0.5.0
opendataloader-pdf[hybrid]>=0.5.0
docling>=2.0.0
marker-pdf>=1.0.0
pymupdf4llm>=0.0.17
unstructured[pdf]>=0.14.0
unstructured[local-inference]>=0.14.0   # for hi_res

# Evaluation
pandas>=2.0
rapidfuzz>=3.0
tqdm>=4.65
pyyaml>=6.0
jinja2>=3.1          # for report generation
tabulate>=0.9

# Optional: GPU support for marker
# torch>=2.0  (install separately per CUDA version)
```

### 4.2 `config.yaml`

```yaml
corpus_dir: corpus/raw
ground_truth_dir: corpus/ground_truth
output_dir: outputs
report_dir: reports

parsers:
  opendataloader_heuristic:
    enabled: true
    timeout_per_page: 5        # seconds
  opendataloader_hybrid:
    enabled: true
    hybrid_port: 5002
    timeout_per_page: 30
  docling:
    enabled: true
    timeout_per_page: 10
  marker:
    enabled: true
    timeout_per_page: 120      # marker is slow; skip on CPU-only if desired
    require_gpu: false         # set true to skip if no GPU detected
  pymupdf4llm:
    enabled: true
    timeout_per_page: 5
  unstructured_fast:
    enabled: true
    strategy: fast
    timeout_per_page: 5
  unstructured_hires:
    enabled: true
    strategy: hi_res
    timeout_per_page: 60

evaluation:
  table_cell_similarity_threshold: 0.85   # rapidfuzz token_sort_ratio
  footnote_anchor_match: exact            # or "fuzzy"
  weights:
    tier1: 1.0
    tier2: 1.5
    tier3: 2.0
```

### 4.3 `parsers/run_opendataloader.py`

```python
"""OpenDataLoader heuristic-only mode runner."""
import time, json, sys
from pathlib import Path
import yaml
from opendataloader_pdf import PDFLoader

def run(pdf_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    loader = PDFLoader(str(pdf_path))

    t0 = time.perf_counter()
    docs = loader.load()           # returns list of Document objects
    elapsed = time.perf_counter() - t0

    pages = len(docs)
    out = {
        "parser": "opendataloader_heuristic",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "content": [
            {
                "page": i,
                "markdown": doc.page_content,
                "metadata": doc.metadata,
            }
            for i, doc in enumerate(docs)
        ],
    }

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text("\n\n".join(d.page_content for d in docs))
    print(f"[ODL-heuristic] {stem}: {pages}p in {elapsed:.2f}s ({out['s_per_page']}s/p)")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    out_base = Path(cfg["output_dir"]) / "opendataloader_heuristic"
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, out_base)
```

### 4.4 `parsers/run_opendataloader_hybrid.py`

```python
"""OpenDataLoader hybrid mode (requires: opendataloader-pdf-hybrid --port 5002 --force-ocr)."""
import time, json, subprocess, sys
from pathlib import Path
import yaml
from opendataloader_pdf import PDFLoader

def run(pdf_path: Path, output_dir: Path, hybrid_port: int = 5002):
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use hybrid backend via CLI flag (or environment variable)
    import os
    os.environ["OPENDATALOADER_HYBRID_PORT"] = str(hybrid_port)

    loader = PDFLoader(str(pdf_path), hybrid=True)
    t0 = time.perf_counter()
    docs = loader.load()
    elapsed = time.perf_counter() - t0

    pages = len(docs)
    out = {
        "parser": "opendataloader_hybrid",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "content": [
            {"page": i, "markdown": doc.page_content, "metadata": doc.metadata}
            for i, doc in enumerate(docs)
        ],
    }

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text("\n\n".join(d.page_content for d in docs))
    print(f"[ODL-hybrid] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    out_base = Path(cfg["output_dir"]) / "opendataloader_hybrid"
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, out_base, hybrid_port=cfg["parsers"]["opendataloader_hybrid"]["hybrid_port"])
```

### 4.5 `parsers/run_docling.py`

```python
"""Docling runner — outputs DoclingDocument as Markdown + JSON."""
import time, json
from pathlib import Path
import yaml
from docling.document_converter import DocumentConverter

def run(pdf_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()

    t0 = time.perf_counter()
    result = converter.convert(str(pdf_path))
    elapsed = time.perf_counter() - t0

    doc = result.document
    md_text = doc.export_to_markdown()
    doc_dict = doc.export_to_dict()

    pages = len(doc.pages) if hasattr(doc, "pages") else 1
    meta = {
        "parser": "docling",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
    }
    doc_dict["_benchmark_meta"] = meta

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text(md_text)
    print(f"[Docling] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    out_base = Path(cfg["output_dir"]) / "docling"
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, out_base)
```

### 4.6 `parsers/run_marker.py`

```python
"""Marker runner."""
import time, json
from pathlib import Path
import yaml
from marker.convert import convert_single_pdf
from marker.models import load_all_models

_models = None

def get_models():
    global _models
    if _models is None:
        _models = load_all_models()
    return _models

def run(pdf_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    models = get_models()

    t0 = time.perf_counter()
    full_text, images, out_meta = convert_single_pdf(str(pdf_path), models)
    elapsed = time.perf_counter() - t0

    pages = out_meta.get("pages", 1)
    result = {
        "parser": "marker",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "metadata": out_meta,
    }

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text(full_text)
    print(f"[Marker] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    out_base = Path(cfg["output_dir"]) / "marker"
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, out_base)
```

### 4.7 `parsers/run_pymupdf4llm.py`

```python
"""PyMuPDF4LLM runner."""
import time, json
from pathlib import Path
import yaml
import pymupdf4llm
import fitz  # PyMuPDF

def run(pdf_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages = doc.page_count
    doc.close()

    t0 = time.perf_counter()
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    elapsed = time.perf_counter() - t0

    result = {
        "parser": "pymupdf4llm",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
    }

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text(md_text)
    print(f"[PyMuPDF4LLM] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    out_base = Path(cfg["output_dir"]) / "pymupdf4llm"
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, out_base)
```

### 4.8 `parsers/run_unstructured_fast.py`

```python
"""Unstructured fast-strategy runner."""
import time, json
from pathlib import Path
import yaml
from unstructured.partition.pdf import partition_pdf

def run(pdf_path: Path, output_dir: Path, strategy: str = "fast"):
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    elements = partition_pdf(filename=str(pdf_path), strategy=strategy)
    elapsed = time.perf_counter() - t0

    pages = max((e.metadata.page_number or 1 for e in elements), default=1)
    serialized = [
        {
            "type": type(e).__name__,
            "text": e.text,
            "page": getattr(e.metadata, "page_number", None),
        }
        for e in elements
    ]
    result = {
        "parser": f"unstructured_{strategy}",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "elements": serialized,
    }

    md_parts = []
    for e in elements:
        t = type(e).__name__
        if t == "Table":
            md_parts.append(e.metadata.text_as_html or e.text)
        elif t.startswith("Title") or t.startswith("Header"):
            md_parts.append(f"## {e.text}")
        else:
            md_parts.append(e.text)

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text("\n\n".join(md_parts))
    print(f"[Unstructured-{strategy}] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, Path(cfg["output_dir"]) / "unstructured_fast", strategy="fast")
```

### 4.9 `parsers/run_unstructured_hires.py`

```python
"""Unstructured hi_res strategy (uses detectron2 layout model)."""
# Same as run_unstructured_fast.py but strategy="hi_res"
# Separate file for independent enable/disable via config

import time, json
from pathlib import Path
import yaml
from unstructured.partition.pdf import partition_pdf

def run(pdf_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    elements = partition_pdf(filename=str(pdf_path), strategy="hi_res",
                             infer_table_structure=True)
    elapsed = time.perf_counter() - t0

    pages = max((e.metadata.page_number or 1 for e in elements), default=1)
    serialized = [
        {"type": type(e).__name__, "text": e.text,
         "html": getattr(e.metadata, "text_as_html", None),
         "page": getattr(e.metadata, "page_number", None)}
        for e in elements
    ]
    result = {
        "parser": "unstructured_hires",
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "elements": serialized,
    }

    md_parts = []
    for e in elements:
        t = type(e).__name__
        if t == "Table":
            md_parts.append(e.metadata.text_as_html or e.text)
        else:
            md_parts.append(e.text)

    stem = pdf_path.stem
    (output_dir / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output_dir / f"{stem}.md").write_text("\n\n".join(md_parts))
    print(f"[Unstructured-hires] {stem}: {pages}p in {elapsed:.2f}s")


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    corpus = Path(cfg["corpus_dir"])
    for pdf in sorted(corpus.glob("*.pdf")):
        run(pdf, Path(cfg["output_dir"]) / "unstructured_hires")
```

---

## 5. Ground Truth Schema

For each PDF in the corpus, create `corpus/ground_truth/{stem}.json` by hand (open PDF in viewer and annotate):

```json
{
  "source": "cisco_400zr.pdf",
  "tier": 2,
  "tables": [
    {
      "table_id": "optical_specs_qpsk",
      "page_start": 4,
      "page_end": 5,
      "title": "Optical Specifications – QPSK Mode",
      "headers": ["Parameter", "Unit", "Min", "Typ", "Max", "Notes"],
      "rows": [
        {
          "Parameter": "Tx Output Power",
          "Unit": "dBm",
          "Min": "-10.0",
          "Typ": null,
          "Max": "0.0",
          "Notes": "1"
        },
        {
          "Parameter": "Receiver Sensitivity",
          "Unit": "dBm",
          "Min": null,
          "Typ": "-18.0",
          "Max": null,
          "Notes": "2"
        }
      ],
      "footnotes": {
        "1": "Measured at OMA; temperature range –5°C to +75°C",
        "2": "BER < 1×10⁻³, OSNR = 14 dB"
      },
      "modulation_block": "QPSK",
      "multi_page_span": true,
      "has_merged_cells": true
    }
  ],
  "structure": {
    "section_order": [
      "Product Overview",
      "Features",
      "Optical Specifications",
      "Electrical Specifications",
      "Management Interface",
      "Mechanical Dimensions",
      "Ordering Information"
    ],
    "total_tables": 5,
    "total_footnotes": 12
  }
}
```

**Annotation guidelines:**
- Record every table separately, even if they share a page
- For merged cells, record the effective value in each logical row
- Footnote keys must match the superscript character in the table (¹ → "1", * → "*")
- For multi-modulation tables, split into logical modulation blocks in ground truth
- `null` = cell is genuinely empty; do not infer values

---

## 6. Evaluation Metrics

### 6.1 Table Cell Accuracy (TCA)

For each table in ground truth:
1. Extract the corresponding table from parser output (by table_id title match)
2. Align ground-truth rows to parsed rows using header matching
3. For each cell: `score = rapidfuzz.token_sort_ratio(gt_cell, parsed_cell) / 100`
4. `TCA = mean(all cell scores)` for the table

**Special cases for optical datasheets:**
- Numeric tolerance: `"–3.0"` vs `"-3.0"` → normalize sign before comparison
- Unit variants: `"dBm"` vs `"dB(m)"` → strip parentheses, lowercase
- Missing Typ/Min/Max: if parser leaves null where GT has value → score 0; if GT is null and parser is empty → score 1

### 6.2 Footnote Linkage Score (FLS)

For each table:
1. **Anchor detection:** Did the parser preserve footnote markers in cell text? (e.g., "–10.0 ¹" not just "–10.0")
2. **Body detection:** Did the parser capture the footnote text at all (anywhere in the document)?
3. **Linkage:** Is the footnote body associated with the correct anchor?

```
FLS = (anchor_detected * 0.3) + (body_detected * 0.3) + (correctly_linked * 0.4)
```

### 6.3 Structure Score (SS)

- **Section heading detection:** ratio of GT section headings found in parser output (fuzzy match > 0.85)
- **Table count accuracy:** `1 - |parsed_tables - gt_tables| / gt_tables` (clipped to 0)
- **Table order preserved:** Kendall's tau of parsed table order vs GT order

```
SS = (heading_recall * 0.4) + (table_count_accuracy * 0.3) + (table_order_tau * 0.3)
```

### 6.4 Multi-Modulation Normalization Score (MMNS)

Specific to optical datasheets — measures whether the parser correctly separates QPSK / 8-QAM / 16-QAM blocks when they appear as sub-sections within a single table:

- Did the parser emit 1 merged table or correctly segmented sub-tables?
- Are QPSK-specific rows not mixed with 16-QAM rows?

Binary per table (0 or 1), averaged across applicable tables.

### 6.5 Composite Score

```
Composite = (TCA * 0.40) + (FLS * 0.25) + (SS * 0.20) + (MMNS * 0.15)
```

With tier weighting applied:
```
Weighted_Composite = sum(tier_weight[tier] * composite[pdf]) / sum(tier_weight[tier])
```

### 6.6 Speed Score

```
Speed_score = 1 / (1 + log10(1 + s_per_page))   # normalized 0–1, lower latency = higher score
```

---

## 7. Evaluation Scripts

### 7.1 `evaluation/evaluate_tables.py`

```python
"""Table Cell Accuracy and Footnote Linkage Scoring."""
import json, re
from pathlib import Path
from rapidfuzz import fuzz
from typing import Optional

def normalize_cell(text: Optional[str]) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("−", "-").replace("–", "-")   # unicode minus/en-dash → hyphen
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    return text

def cell_score(gt: Optional[str], pred: Optional[str]) -> float:
    gt_n = normalize_cell(gt)
    pred_n = normalize_cell(pred)
    if gt_n == "" and pred_n == "":
        return 1.0
    if gt_n == "" or pred_n == "":
        return 0.0
    return fuzz.token_sort_ratio(gt_n, pred_n) / 100.0

def score_table(gt_table: dict, parsed_tables: list) -> dict:
    """Find best-matching parsed table and score cells."""
    title = gt_table["table_id"]

    # 1. Find matching table in parsed output by title similarity
    best_match = None
    best_title_score = 0.0
    for pt in parsed_tables:
        s = fuzz.token_sort_ratio(title.lower(), pt.get("title", "").lower()) / 100
        if s > best_title_score:
            best_title_score = s
            best_match = pt

    if best_match is None or best_title_score < 0.5:
        return {"table_id": title, "tca": 0.0, "fls": 0.0, "found": False}

    # 2. TCA: score each GT row
    gt_rows = gt_table["rows"]
    pred_rows = best_match.get("rows", [])
    cell_scores = []

    for gt_row in gt_rows:
        # Find best matching pred row by first column
        key_col = gt_table["headers"][0]
        gt_key = normalize_cell(gt_row.get(key_col))
        best_row = None
        best_row_score = 0.0
        for pr in pred_rows:
            s = fuzz.token_sort_ratio(gt_key, normalize_cell(pr.get(key_col, ""))) / 100
            if s > best_row_score:
                best_row_score = s
                best_row = pr

        if best_row and best_row_score > 0.7:
            for col in gt_table["headers"]:
                if col == key_col:
                    continue
                cell_scores.append(cell_score(gt_row.get(col), best_row.get(col)))
        else:
            # Row not found → all cells score 0
            cell_scores.extend([0.0] * (len(gt_table["headers"]) - 1))

    tca = sum(cell_scores) / max(len(cell_scores), 1)

    # 3. FLS: footnote linkage
    gt_footnotes = gt_table.get("footnotes", {})
    pred_text = best_match.get("raw_text", "")
    anchors_found = sum(1 for k in gt_footnotes if k in pred_text)
    bodies_found = sum(
        1 for v in gt_footnotes.values()
        if fuzz.partial_ratio(v.lower(), pred_text.lower()) > 75
    )
    n = max(len(gt_footnotes), 1)
    fls = (anchors_found / n * 0.5) + (bodies_found / n * 0.5)

    return {
        "table_id": title,
        "tca": round(tca, 4),
        "fls": round(fls, 4),
        "found": True,
        "title_match_score": round(best_title_score, 4),
    }


def score_pdf(gt_path: Path, pred_md_path: Path, pred_json_path: Path) -> dict:
    gt = json.loads(gt_path.read_text())
    
    # Extract tables from parser output JSON if structured, else return empty
    try:
        pred = json.loads(pred_json_path.read_text())
        parsed_tables = pred.get("tables", [])
    except Exception:
        parsed_tables = []

    results = [score_table(t, parsed_tables) for t in gt["tables"]]

    tca_mean = sum(r["tca"] for r in results) / max(len(results), 1)
    fls_mean = sum(r["fls"] for r in results) / max(len(results), 1)

    return {
        "pdf": gt_path.stem,
        "tier": gt.get("tier", 1),
        "tca": round(tca_mean, 4),
        "fls": round(fls_mean, 4),
        "table_results": results,
    }
```

### 7.2 `evaluation/aggregate_scores.py`

```python
"""Aggregate per-PDF scores into parser-level benchmark table."""
import json, time
from pathlib import Path
import pandas as pd
import yaml

PARSERS = [
    "opendataloader_heuristic",
    "opendataloader_hybrid",
    "docling",
    "marker",
    "pymupdf4llm",
    "unstructured_fast",
    "unstructured_hires",
]

TIER_WEIGHTS = {1: 1.0, 2: 1.5, 3: 2.0}

def load_scores(results_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(results_dir.glob("*.json")):
        data = json.loads(f.read_text())
        data["weight"] = TIER_WEIGHTS.get(data.get("tier", 1), 1.0)
        rows.append(data)
    return pd.DataFrame(rows)

def compute_composite(df: pd.DataFrame) -> pd.Series:
    return (
        df["tca"] * 0.40 +
        df["fls"] * 0.25 +
        df.get("ss", pd.Series(0.0, index=df.index)) * 0.20 +
        df.get("mmns", pd.Series(0.0, index=df.index)) * 0.15
    )

def aggregate(output_base: Path, gt_dir: Path) -> pd.DataFrame:
    summary_rows = []
    for parser in PARSERS:
        results_dir = output_base / parser / "scores"
        if not results_dir.exists():
            continue
        df = load_scores(results_dir)
        if df.empty:
            continue
        df["composite"] = compute_composite(df)
        weighted_composite = (df["composite"] * df["weight"]).sum() / df["weight"].sum()
        weighted_tca = (df["tca"] * df["weight"]).sum() / df["weight"].sum()
        weighted_fls = (df["fls"] * df["weight"]).sum() / df["weight"].sum()
        avg_spp = df["s_per_page"].mean() if "s_per_page" in df.columns else float("nan")
        summary_rows.append({
            "parser": parser,
            "composite": round(weighted_composite, 4),
            "tca": round(weighted_tca, 4),
            "fls": round(weighted_fls, 4),
            "s_per_page": round(avg_spp, 3),
            "pdfs_evaluated": len(df),
        })
    return pd.DataFrame(summary_rows).sort_values("composite", ascending=False)


if __name__ == "__main__":
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    summary = aggregate(Path(cfg["output_dir"]), Path(cfg["ground_truth_dir"]))
    print(summary.to_string(index=False))
    summary.to_csv(Path(cfg["report_dir"]) / "summary.csv", index=False)
    print("\nSaved to reports/summary.csv")
```

---

## 8. Run All Script

### `run_all.sh`

```bash
#!/usr/bin/env bash
set -e

echo "=== Optical Transceiver Datasheet Parser Benchmark ==="

# Activate venv
source venv/bin/activate

# Optional: start ODL hybrid backend in background
# opendataloader-pdf-hybrid --port 5002 --force-ocr &
# ODL_PID=$!
# sleep 5

# Run all parsers
echo "--- Running OpenDataLoader (heuristic) ---"
python parsers/run_opendataloader.py

echo "--- Running OpenDataLoader (hybrid) ---"
python parsers/run_opendataloader_hybrid.py

echo "--- Running Docling ---"
python parsers/run_docling.py

echo "--- Running Marker ---"
python parsers/run_marker.py

echo "--- Running PyMuPDF4LLM ---"
python parsers/run_pymupdf4llm.py

echo "--- Running Unstructured (fast) ---"
python parsers/run_unstructured_fast.py

echo "--- Running Unstructured (hi_res) ---"
python parsers/run_unstructured_hires.py

# Run evaluation
echo "--- Evaluating ---"
python evaluation/evaluate_tables.py
python evaluation/evaluate_footnotes.py
python evaluation/evaluate_structure.py
python evaluation/aggregate_scores.py

# kill $ODL_PID 2>/dev/null || true

echo "=== Done. See reports/summary.csv ==="
```

---

## 9. Qualitative Checklist (Manual Review)

After running quantitative scores, do a manual spot-check on 2–3 PDFs per parser using this checklist. Record pass/fail in `reports/qualitative_review.csv`.

### Table Normalization Checklist

| Check | What to look for |
|-------|-----------------|
| **Merged cell expansion** | Tx Power row spanning QPSK/8QAM/16QAM sub-columns — are values correctly placed in each column? |
| **Min/Typ/Max preserved** | All three values in separate cells, not concatenated as "–3 / – / 0" in one cell |
| **Unit row handling** | "(dBm)" header row — does it appear as a separate row or correctly merged into parameter name? |
| **Multi-page continuation** | Table split across pages — is it one table or two in the output? |
| **Rotated text headers** | Some Nokia/Ericsson datasheets use 90°-rotated column headers — are they captured at all? |
| **Symbol normalization** | ≥ → `>=`, ≤ → `<=`, µ → `u` or `micro`, ° → `deg` — does output normalize or preserve? |

### Footnote Linkage Checklist

| Check | What to look for |
|-------|-----------------|
| **Superscript preservation** | `–10.0¹` — is the ¹ preserved or dropped? |
| **Footnote body location** | Footnotes at page bottom — captured at all? Captured as part of body text or correctly tagged? |
| **Cross-page footnotes** | Footnote defined on page 5, referenced on page 4 — linked? |
| **Symbol footnotes** | `*`, `†`, `‡` markers — preserved and matched? |

---

## 10. Cursor Prompt

Use the following prompt verbatim when opening this spec in Cursor:

---

```
I need you to implement a PDF parser benchmark for optical transceiver datasheets.
Follow the specification in `optical_datasheet_parser_benchmark_spec.md` exactly.

Implementation steps (do them in order):

1. Create the directory structure from §3 of the spec.

2. Create `requirements.txt` from §4.1.

3. Create `config.yaml` from §4.2.

4. Implement all 7 parser runner scripts from §4.3–4.9.
   - Each script must be runnable standalone: `python parsers/run_X.py`
   - Each must write both a .md and .json output per PDF
   - Each must handle exceptions per-PDF and continue (don't crash the whole run)
   - Log elapsed time and s/page to stdout for every PDF

5. Implement the ground truth schema loader in `evaluation/ground_truth.py`:
   - Load and validate JSON against the schema in §5
   - Raise clear errors if required fields are missing

6. Implement `evaluation/evaluate_tables.py` from §7.1:
   - TCA and FLS scoring
   - Output per-PDF score JSON to `outputs/{parser}/scores/{stem}.json`

7. Implement `evaluation/evaluate_structure.py`:
   - Structure Score (SS) as defined in §6.3
   - Use the `structure.section_order` list from ground truth

8. Implement `evaluation/aggregate_scores.py` from §7.2:
   - Weighted composite across tiers
   - Output to `reports/summary.csv` and print ranked table

9. Implement `run_all.sh` from §8.

10. Create a `README.md` explaining:
    - How to install dependencies
    - How to add a new PDF to corpus (including ground truth annotation steps)
    - How to run the full benchmark
    - How to interpret scores

Important constraints:
- Do NOT mock any parser output. Every runner must call the real library.
- If a library import fails, catch ImportError and write a placeholder output
  with `{"error": "library not installed", "parser": "..."}` so scoring still runs.
- All paths must be relative to the project root (no hardcoded absolute paths).
- Python 3.10+ compatible.
- Type hints on all public functions.
- Each parser runner should respect the `timeout_per_page` from config by
  wrapping conversion in a threading.Timer kill if it exceeds
  `timeout_per_page * page_count * 1.5`.
```

---

## 11. Expected Results & Interpretation Guide

Based on the general benchmark data and optical datasheet characteristics:

| Parser | Expected Composite (optical) | Known weakness on datasheets |
|--------|------------------------------|------------------------------|
| **ODL hybrid** | ~0.82–0.88 | Heuristic table finding may miss rotated headers |
| **Docling** | ~0.80–0.87 | Strong table structure; footnote linkage needs post-processing |
| **Marker** | ~0.75–0.82 | Good on Tier 3 (scanned); very slow; may hallucinate units |
| **Unstructured hi_res** | ~0.72–0.80 | Strong OCR; table HTML output not always clean Markdown |
| **ODL heuristic** | ~0.65–0.75 | Fast but weak table structure (0.49 in general bench) |
| **PyMuPDF4LLM** | ~0.55–0.68 | Fast, good for Tier 1; totally breaks on merged cells |
| **Unstructured fast** | ~0.45–0.60 | Zero table extraction; useful only for reading order |

**What to watch for in optical datasheets specifically:**
- All parsers struggle with the CMIS application code tables (hex notation, many columns)
- Nokia datasheets use non-standard column separators (dots, not lines) — tests OCR robustness
- Smartoptics PDFs are native but have very dense multi-level headers — tests structural parsing
- Ericsson PDFs sometimes embed optical spec tables as SVG — most parsers will miss these entirely

---

*Spec version 1.0 | Designed for Python 3.10+ | Tested parser versions: see requirements.txt*
