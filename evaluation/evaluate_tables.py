from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from rapidfuzz import fuzz

from evaluation.ground_truth import load_ground_truth_file
from parsers.common import append_jsonl


def normalize_cell(text: Optional[str]) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    text = text.replace("dB(m)", "dbm")
    return text


def cell_score(gt: Optional[str], pred: Optional[str]) -> float:
    gt_n = normalize_cell(gt)
    pred_n = normalize_cell(pred)
    if gt_n == "" and pred_n == "":
        return 1.0
    if gt_n == "" or pred_n == "":
        return 0.0
    return fuzz.token_sort_ratio(gt_n, pred_n) / 100.0


def score_table(gt_table: Dict[str, Any], parsed_tables: list[dict[str, Any]]) -> Dict[str, Any]:
    title = gt_table["table_id"]
    best_match = None
    best_title_score = 0.0
    for pt in parsed_tables:
        s = fuzz.token_sort_ratio(title.lower(), str(pt.get("title", "")).lower()) / 100
        if s > best_title_score:
            best_title_score = s
            best_match = pt

    if best_match is None or best_title_score < 0.5:
        return {"table_id": title, "tca": 0.0, "fls": 0.0, "found": False}

    gt_rows = gt_table.get("rows", [])
    pred_rows = best_match.get("rows", [])
    headers = gt_table.get("headers", [])
    if not headers:
        return {"table_id": title, "tca": 0.0, "fls": 0.0, "found": False}

    key_col = headers[0]
    scores = []
    for gt_row in gt_rows:
        gt_key = normalize_cell(gt_row.get(key_col))
        best_row = None
        best_row_score = 0.0
        for pr in pred_rows:
            score = fuzz.token_sort_ratio(gt_key, normalize_cell(pr.get(key_col))) / 100
            if score > best_row_score:
                best_row_score = score
                best_row = pr

        if best_row and best_row_score > 0.7:
            for col in headers[1:]:
                scores.append(cell_score(gt_row.get(col), best_row.get(col)))
        else:
            scores.extend([0.0] * max(0, len(headers) - 1))

    tca = sum(scores) / max(len(scores), 1)

    gt_footnotes = gt_table.get("footnotes", {})
    pred_text = str(best_match.get("raw_text", ""))
    anchors_found = sum(1 for k in gt_footnotes if str(k) in pred_text)
    bodies_found = sum(1 for v in gt_footnotes.values() if fuzz.partial_ratio(str(v).lower(), pred_text.lower()) > 75)
    n = max(1, len(gt_footnotes))
    fls = (anchors_found / n * 0.3) + (bodies_found / n * 0.3) + (min(anchors_found, bodies_found) / n * 0.4)

    return {
        "table_id": title,
        "tca": round(tca, 4),
        "fls": round(fls, 4),
        "found": True,
        "title_match_score": round(best_title_score, 4),
    }


def score_pdf(gt_path: Path, pred_json_path: Path) -> Dict[str, Any]:
    gt = load_ground_truth_file(gt_path)
    try:
        pred = json.loads(pred_json_path.read_text(encoding="utf-8"))
    except Exception:
        pred = {}

    parsed_tables = pred.get("tables", []) if isinstance(pred, dict) else []
    table_results = [score_table(t, parsed_tables) for t in gt.get("tables", [])]
    tca_mean = sum(r["tca"] for r in table_results) / max(1, len(table_results))
    fls_mean = sum(r["fls"] for r in table_results) / max(1, len(table_results))

    return {
        "pdf": gt_path.stem,
        "tier": gt.get("tier", 1),
        "tca": round(tca_mean, 4),
        "fls": round(fls_mean, 4),
        "s_per_page": float(pred.get("s_per_page", 0.0)) if isinstance(pred, dict) else 0.0,
        "table_results": table_results,
    }


def main() -> None:
    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    gt_dir = Path(cfg["ground_truth_dir"])
    output_base = Path(cfg["output_dir"])
    obs_file = Path(cfg["report_dir"]) / "observability" / "events.jsonl"

    parser_names = [k for k, v in cfg.get("parsers", {}).items() if v.get("enabled", True)]
    gt_files = sorted(gt_dir.glob("*.json")) if gt_dir.exists() else []
    if not gt_files:
        print("No ground truth JSON files found. Skipping table/footnote scoring.")
        return

    for parser in parser_names:
        parser_out = output_base / parser
        scores_dir = parser_out / "scores"
        scores_dir.mkdir(parents=True, exist_ok=True)
        for gt_file in gt_files:
            pred_json = parser_out / f"{gt_file.stem}.json"
            if not pred_json.exists():
                continue
            score = score_pdf(gt_file, pred_json)
            score_path = scores_dir / f"{gt_file.stem}.json"
            score_path.write_text(json.dumps(score, indent=2), encoding="utf-8")
            append_jsonl(
                obs_file,
                {
                    "ts": time.time(),
                    "stage": "evaluation_tables",
                    "parser": parser,
                    "pdf": gt_file.stem,
                    "tca": score["tca"],
                    "fls": score["fls"],
                },
            )
        print(f"[evaluate_tables] completed parser={parser}")


if __name__ == "__main__":
    main()
