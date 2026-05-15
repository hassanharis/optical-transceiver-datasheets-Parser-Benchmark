from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml


def summarize_parser(corpus_pdfs: set[str], parser_dir: Path, parser_name: str) -> Dict[str, Any]:
    rows = []
    errors = 0
    for jf in sorted(parser_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("error"):
            errors += 1
        rows.append(
            {
                "pdf": jf.stem,
                "elapsed_s": float(data.get("elapsed_s", 0.0)) if isinstance(data, dict) else 0.0,
                "s_per_page": float(data.get("s_per_page", 0.0)) if isinstance(data, dict) else 0.0,
                "pages": int(data.get("pages", 0)) if isinstance(data, dict) else 0,
            }
        )

    df = pd.DataFrame(rows)
    parsed_pdfs = set(df["pdf"].tolist()) if not df.empty else set()
    missing = len(corpus_pdfs - parsed_pdfs)

    if df.empty:
        return {
            "parser": parser_name,
            "pdfs_expected": len(corpus_pdfs),
            "pdfs_parsed": 0,
            "pdfs_missing": len(corpus_pdfs),
            "errors": errors,
            "total_elapsed_s": 0.0,
            "avg_s_per_page": 0.0,
            "median_s_per_page": 0.0,
            "total_pages": 0,
        }

    return {
        "parser": parser_name,
        "pdfs_expected": len(corpus_pdfs),
        "pdfs_parsed": int(len(df)),
        "pdfs_missing": int(missing),
        "errors": int(errors),
        "total_elapsed_s": round(float(df["elapsed_s"].sum()), 2),
        "avg_s_per_page": round(float(df["s_per_page"].mean()), 3),
        "median_s_per_page": round(float(df["s_per_page"].median()), 3),
        "total_pages": int(df["pages"].sum()),
    }


def main() -> None:
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    corpus_dir = Path(cfg["corpus_dir"])
    output_dir = Path(cfg["output_dir"])
    report_dir = Path(cfg["report_dir"])
    report_dir.mkdir(parents=True, exist_ok=True)

    corpus_pdfs = {p.stem for p in corpus_dir.glob("*.pdf")}
    parser_names = [k for k, v in cfg.get("parsers", {}).items() if v.get("enabled", True)]

    summary_rows: List[Dict[str, Any]] = []
    for parser in parser_names:
        parser_dir = output_dir / parser
        if parser_dir.exists():
            summary_rows.append(summarize_parser(corpus_pdfs, parser_dir, parser))

    df = pd.DataFrame(summary_rows)
    out_csv = report_dir / "runtime_summary.csv"
    df.to_csv(out_csv, index=False)

    if not df.empty:
        print(df.sort_values("avg_s_per_page").to_string(index=False))
    print(f"Saved to {out_csv}")


if __name__ == "__main__":
    main()
