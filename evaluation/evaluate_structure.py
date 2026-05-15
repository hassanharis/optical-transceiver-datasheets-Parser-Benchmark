from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from rapidfuzz import fuzz

from evaluation.ground_truth import load_ground_truth_file
from parsers.common import append_jsonl


def heading_recall(gt_headings: List[str], md_text: str) -> float:
    if not gt_headings:
        return 0.0
    found = 0
    md_lower = md_text.lower()
    for heading in gt_headings:
        if fuzz.partial_ratio(heading.lower(), md_lower) / 100 >= 0.85:
            found += 1
    return found / len(gt_headings)


def estimate_table_count(md_text: str) -> int:
    lines = md_text.splitlines()
    count = 0
    for i in range(0, len(lines) - 1):
        if "|" in lines[i] and "|" in lines[i + 1] and "-" in lines[i + 1]:
            count += 1
    return count


def kendall_tau(labels_a: List[str], labels_b: List[str]) -> float:
    shared = [x for x in labels_a if x in labels_b]
    if len(shared) < 2:
        return 0.0
    order_b = {k: i for i, k in enumerate(labels_b)}
    concordant = 0
    discordant = 0
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            a_i, a_j = shared[i], shared[j]
            if order_b[a_i] < order_b[a_j]:
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom


def score_structure(gt: Dict[str, Any], pred_md: str, pred_json: Dict[str, Any]) -> Dict[str, float]:
    structure = gt.get("structure", {})
    gt_headings = structure.get("section_order", [])
    gt_tables = int(structure.get("total_tables", len(gt.get("tables", [])) or 1))

    hrec = heading_recall(gt_headings, pred_md)
    pred_table_count = len(pred_json.get("tables", [])) if isinstance(pred_json, dict) else estimate_table_count(pred_md)
    table_count_acc = max(0.0, 1.0 - abs(pred_table_count - gt_tables) / max(1, gt_tables))

    gt_order = [t.get("table_id", "") for t in gt.get("tables", [])]
    pred_order = [t.get("title", "") for t in pred_json.get("tables", [])] if isinstance(pred_json, dict) else []
    tau = max(0.0, kendall_tau(gt_order, pred_order))

    mmns = 0.0
    mod_markers = ["qpsk", "8-qam", "16-qam"]
    marker_hits = [m for m in mod_markers if m in pred_md.lower()]
    if marker_hits:
        mmns = 1.0 if len(marker_hits) >= 2 else 0.5

    ss = hrec * 0.4 + table_count_acc * 0.3 + tau * 0.3
    return {"ss": round(ss, 4), "mmns": round(mmns, 4)}


def main() -> None:
    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    gt_dir = Path(cfg["ground_truth_dir"])
    output_base = Path(cfg["output_dir"])
    obs_file = Path(cfg["report_dir"]) / "observability" / "events.jsonl"

    parser_names = [k for k, v in cfg.get("parsers", {}).items() if v.get("enabled", True)]
    gt_files = sorted(gt_dir.glob("*.json")) if gt_dir.exists() else []
    if not gt_files:
        print("No ground truth JSON files found. Skipping structure scoring.")
        return

    for parser in parser_names:
        parser_out = output_base / parser
        scores_dir = parser_out / "scores"
        scores_dir.mkdir(parents=True, exist_ok=True)
        for gt_file in gt_files:
            pred_json_path = parser_out / f"{gt_file.stem}.json"
            pred_md_path = parser_out / f"{gt_file.stem}.md"
            if not pred_json_path.exists() or not pred_md_path.exists():
                continue

            gt = load_ground_truth_file(gt_file)
            pred_json = json.loads(pred_json_path.read_text(encoding="utf-8"))
            pred_md = pred_md_path.read_text(encoding="utf-8", errors="ignore")

            struct_scores = score_structure(gt, pred_md, pred_json)

            score_file = scores_dir / f"{gt_file.stem}.json"
            if score_file.exists():
                score_data = json.loads(score_file.read_text(encoding="utf-8"))
            else:
                score_data = {
                    "pdf": gt_file.stem,
                    "tier": gt.get("tier", 1),
                    "tca": 0.0,
                    "fls": 0.0,
                    "s_per_page": float(pred_json.get("s_per_page", 0.0)),
                    "table_results": [],
                }
            score_data.update(struct_scores)
            score_file.write_text(json.dumps(score_data, indent=2), encoding="utf-8")

            append_jsonl(
                obs_file,
                {
                    "ts": time.time(),
                    "stage": "evaluation_structure",
                    "parser": parser,
                    "pdf": gt_file.stem,
                    "ss": struct_scores["ss"],
                    "mmns": struct_scores["mmns"],
                },
            )
        print(f"[evaluate_structure] completed parser={parser}")


if __name__ == "__main__":
    main()
