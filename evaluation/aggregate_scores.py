from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml

from parsers.common import append_jsonl


def speed_score(s_per_page: float) -> float:
    return 1.0 / (1.0 + math.log10(1.0 + max(0.0, s_per_page)))


def load_scores(results_dir: Path, tier_weights: Dict[int, float]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for file in sorted(results_dir.glob("*.json")):
        item = json.loads(file.read_text(encoding="utf-8"))
        tier = int(item.get("tier", 1))
        item["weight"] = float(tier_weights.get(tier, 1.0))
        item["ss"] = float(item.get("ss", 0.0))
        item["mmns"] = float(item.get("mmns", 0.0))
        item["speed"] = speed_score(float(item.get("s_per_page", 0.0)))
        rows.append(item)
    return pd.DataFrame(rows)


def compute_composite(df: pd.DataFrame) -> pd.Series:
    return df["tca"] * 0.40 + df["fls"] * 0.25 + df["ss"] * 0.20 + df["mmns"] * 0.15


def aggregate(cfg: Dict[str, Any]) -> pd.DataFrame:
    parser_names = [k for k, v in cfg.get("parsers", {}).items() if v.get("enabled", True)]
    output_base = Path(cfg["output_dir"])
    weights_cfg = cfg.get("evaluation", {}).get("weights", {})
    tier_weights = {
        1: float(weights_cfg.get("tier1", 1.0)),
        2: float(weights_cfg.get("tier2", 1.5)),
        3: float(weights_cfg.get("tier3", 2.0)),
    }

    rows = []
    for parser in parser_names:
        score_dir = output_base / parser / "scores"
        if not score_dir.exists():
            continue
        df = load_scores(score_dir, tier_weights)
        if df.empty:
            continue
        df["composite"] = compute_composite(df)
        weight_sum = df["weight"].sum()
        rows.append(
            {
                "parser": parser,
                "composite": round(float((df["composite"] * df["weight"]).sum() / weight_sum), 4),
                "tca": round(float((df["tca"] * df["weight"]).sum() / weight_sum), 4),
                "fls": round(float((df["fls"] * df["weight"]).sum() / weight_sum), 4),
                "ss": round(float((df["ss"] * df["weight"]).sum() / weight_sum), 4),
                "mmns": round(float((df["mmns"] * df["weight"]).sum() / weight_sum), 4),
                "speed_score": round(float(df["speed"].mean()), 4),
                "s_per_page": round(float(df["s_per_page"].mean()), 3),
                "pdfs_evaluated": int(len(df)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["parser", "composite", "tca", "fls", "ss", "mmns", "speed_score", "s_per_page", "pdfs_evaluated"])
    return pd.DataFrame(rows).sort_values("composite", ascending=False)


def main() -> None:
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    report_dir = Path(cfg["report_dir"])
    report_dir.mkdir(parents=True, exist_ok=True)
    obs_file = report_dir / "observability" / "events.jsonl"

    summary = aggregate(cfg)
    summary_path = report_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)
    if summary.empty:
        print("No score files found. summary.csv written with headers only.")
    else:
        print(summary.to_string(index=False))
    print(f"Saved to {summary_path}")

    append_jsonl(
        obs_file,
        {
            "ts": time.time(),
            "stage": "aggregation",
            "rows": int(len(summary)),
            "summary_path": str(summary_path),
        },
    )


if __name__ == "__main__":
    main()
