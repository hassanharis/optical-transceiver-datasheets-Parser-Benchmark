from __future__ import annotations

import csv
import json
import math
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean
from typing import Any

import yaml
from rapidfuzz import fuzz


FOOTNOTE_MARKERS = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("µ", "u").replace("μ", "u")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_`#|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = text.replace("db(m)", "dbm")
    return text


def flatten_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(flatten_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(flatten_values(item))
    elif value is not None:
        text = str(value).strip()
        if text:
            values.append(text)
    return values


def row_text(row: dict[str, Any]) -> str:
    return normalize_text(" ".join(flatten_values(row)))


def table_text(table: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("table_id", "title", "raw_text"):
        if table.get(key):
            parts.append(str(table[key]))
    parts.extend(flatten_values(table.get("headers", [])))
    parts.extend(flatten_values(table.get("rows", [])))
    return normalize_text(" ".join(parts))


class TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._current_row = []
        elif tag.lower() in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(unescape(" ".join(self._current_cell)).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def parse_html_table(html: str, fallback_text: str, title: str) -> dict[str, Any]:
    parser = TableHTMLParser()
    try:
        parser.feed(html)
    except Exception:
        parser.rows = []
    rows = parser.rows
    if not rows:
        return {"title": title, "headers": [], "rows": [{"text": fallback_text}], "raw_text": fallback_text}

    headers = rows[0]
    if len(rows) > 1 and len(headers) >= 2:
        data_rows = rows[1:]
    else:
        width = max(len(row) for row in rows)
        headers = [f"Column {idx + 1}" for idx in range(width)]
        data_rows = rows

    normalized_rows: list[dict[str, str]] = []
    for row in data_rows:
        item: dict[str, str] = {}
        for idx, header in enumerate(headers):
            item[header or f"Column {idx + 1}"] = row[idx] if idx < len(row) else ""
        if any(value.strip() for value in item.values()):
            normalized_rows.append(item)

    return {
        "title": title,
        "headers": headers,
        "rows": normalized_rows,
        "raw_text": fallback_text or "\n".join(" | ".join(row) for row in rows),
    }


def extract_doc_tables(pred: dict[str, Any]) -> list[dict[str, Any]]:
    tables = pred.get("tables", [])
    if isinstance(tables, list) and tables:
        return tables

    element_tables: list[dict[str, Any]] = []
    last_title = "table"
    elements = pred.get("elements", [])
    for element in elements if isinstance(elements, list) else []:
        if not isinstance(element, dict):
            continue
        element_type = normalize_text(element.get("type"))
        text = str(element.get("text") or "")
        if element_type in {"title", "header"} and text.strip():
            last_title = text.strip()
        elif element_type == "table":
            html = str(element.get("html") or "")
            element_tables.append(parse_html_table(html, text, last_title))
    return element_tables


def parser_text(pred_json_path: Path, pred_md_path: Path) -> str:
    chunks: list[str] = []
    if pred_md_path.exists():
        chunks.append(pred_md_path.read_text(encoding="utf-8", errors="ignore"))
    if pred_json_path.exists():
        chunks.append(pred_json_path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def is_reviewed_non_empty(gt: dict[str, Any]) -> bool:
    tables = gt.get("tables", [])
    if not isinstance(tables, list) or not tables:
        return False
    return not any(isinstance(table, dict) and table.get("needs_review") for table in tables)


def load_reviewed_gt(gt_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    reviewed: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(gt_dir.glob("*.json"), key=lambda p: p.name.lower()):
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_reviewed_non_empty(data):
            reviewed.append((path, data))
    return reviewed


def best_table_match(gt_table: dict[str, Any], pred_tables: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int, float]:
    if not pred_tables:
        return None, -1, 0.0
    gt_sig = table_text(gt_table)
    best: tuple[dict[str, Any] | None, int, float] = (None, -1, 0.0)
    for idx, pred_table in enumerate(pred_tables):
        pred_sig = table_text(pred_table)
        score = fuzz.token_set_ratio(gt_sig, pred_sig) / 100.0
        if score > best[2]:
            best = (pred_table, idx, score)
    return best


def score_gt_cell_against_row(gt_cell: Any, pred_row: dict[str, Any]) -> float:
    gt_norm = normalize_text(gt_cell)
    pred_values = [normalize_text(value) for value in flatten_values(pred_row)]
    pred_values = [value for value in pred_values if value]
    if not gt_norm:
        return 1.0
    if not pred_values:
        return 0.0
    exactish = max((fuzz.token_sort_ratio(gt_norm, value) / 100.0 for value in pred_values), default=0.0)
    containment = max((fuzz.partial_ratio(gt_norm, value) / 100.0 for value in pred_values), default=0.0)
    return max(exactish, containment * 0.92)


def score_tca(gt_table: dict[str, Any], pred_table: dict[str, Any] | None) -> float:
    if pred_table is None:
        return 0.0
    gt_rows = gt_table.get("rows", [])
    pred_rows = pred_table.get("rows", [])
    if not isinstance(gt_rows, list) or not isinstance(pred_rows, list) or not gt_rows:
        return 0.0

    pred_row_texts = [row_text(row) for row in pred_rows if isinstance(row, dict)]
    pred_dict_rows = [row for row in pred_rows if isinstance(row, dict)]
    cell_scores: list[float] = []
    for gt_row in gt_rows:
        if not isinstance(gt_row, dict):
            continue
        gt_row_norm = row_text(gt_row)
        if not gt_row_norm:
            continue
        best_idx = -1
        best_score = 0.0
        for idx, pred_norm in enumerate(pred_row_texts):
            score = fuzz.token_set_ratio(gt_row_norm, pred_norm) / 100.0
            if score > best_score:
                best_idx = idx
                best_score = score
        if best_idx < 0 or best_score < 0.28:
            non_empty = [value for value in gt_row.values() if normalize_text(value)]
            cell_scores.extend([0.0] * len(non_empty))
            continue
        pred_row = pred_dict_rows[best_idx]
        for value in gt_row.values():
            if normalize_text(value):
                cell_scores.append(score_gt_cell_against_row(value, pred_row))
    return mean(cell_scores) if cell_scores else 0.0


def superscript_marker(marker: str) -> str:
    return "".join(FOOTNOTE_MARKERS.get(ch, ch) for ch in marker)


def marker_regex(marker: str) -> re.Pattern[str]:
    sup = re.escape(superscript_marker(marker))
    plain = re.escape(marker)
    return re.compile(rf"({sup}|(?<!\d){plain}\s*[\)\].:]|\[{plain}\]|\({plain}\))", re.IGNORECASE)


def score_fls(gt_table: dict[str, Any], pred_table: dict[str, Any] | None, full_pred_text: str) -> tuple[float | None, int]:
    footnotes = gt_table.get("footnotes", {})
    if not isinstance(footnotes, dict) or not footnotes:
        return None, 0

    pred_table_text = table_text(pred_table or {})
    full_norm = normalize_text(full_pred_text)
    scores: list[float] = []
    for marker, body in footnotes.items():
        marker_s = str(marker)
        body_norm = normalize_text(body)
        anchor = bool(marker_regex(marker_s).search(pred_table_text))
        body_score = fuzz.partial_ratio(body_norm, full_norm) / 100.0 if body_norm else 0.0
        body_found = body_score >= 0.72

        linked = False
        if anchor and body_found:
            raw = full_pred_text.lower()
            body_start = raw.find(str(body).lower()[: min(40, len(str(body)))])
            if body_start >= 0:
                window = raw[max(0, body_start - 80) : body_start + 80]
                linked = bool(marker_regex(marker_s).search(normalize_text(window)))
            else:
                linked = bool(marker_regex(marker_s).search(full_norm)) and body_score >= 0.82

        scores.append((0.3 if anchor else 0.0) + (0.3 if body_found else 0.0) + (0.4 if linked else 0.0))
    return mean(scores), len(scores)


def heading_recall(gt_headings: list[str], pred_text: str) -> float:
    headings = [normalize_text(h) for h in gt_headings if normalize_text(h)]
    if not headings:
        return 1.0
    pred_norm = normalize_text(pred_text)
    return mean(1.0 if fuzz.partial_ratio(heading, pred_norm) / 100.0 >= 0.85 else 0.0 for heading in headings)


def kendall_tau(indices: list[int]) -> float:
    matched = [idx for idx in indices if idx >= 0]
    if len(matched) < 2:
        return 1.0 if len(matched) == len(indices) else 0.0
    concordant = 0
    discordant = 0
    for i in range(len(matched)):
        for j in range(i + 1, len(matched)):
            if matched[i] <= matched[j]:
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return 0.0
    return max(0.0, (concordant - discordant) / denom)


def score_structure(gt: dict[str, Any], pred_tables: list[dict[str, Any]], pred_text: str, match_indices: list[int]) -> float:
    gt_tables = [table for table in gt.get("tables", []) if isinstance(table, dict)]
    hrec = heading_recall(gt.get("structure", {}).get("section_order", []), pred_text)
    table_count = max(0.0, 1.0 - abs(len(pred_tables) - len(gt_tables)) / max(1, len(gt_tables)))
    order = kendall_tau(match_indices)
    return hrec * 0.4 + table_count * 0.3 + order * 0.3


def modulation_markers(text: str) -> set[str]:
    norm = normalize_text(text)
    markers = set()
    if "qpsk" in norm or "dqpsk" in norm:
        markers.add("qpsk")
    if re.search(r"\b8\s*-?\s*qam\b", norm):
        markers.add("8qam")
    if re.search(r"\b16\s*-?\s*qam\b", norm):
        markers.add("16qam")
    return markers


def score_mmns(gt: dict[str, Any], pred_text: str) -> float | None:
    gt_text = table_text({"rows": gt.get("tables", []), "title": gt.get("source", "")})
    gt_markers = modulation_markers(gt_text)
    if len(gt_markers) < 2:
        return None
    pred_markers = modulation_markers(pred_text)
    recall = len(gt_markers & pred_markers) / len(gt_markers)
    mixed_penalty = 0.0
    if len(gt_markers) >= 2:
        one_line_hits = 0
        for line in pred_text.splitlines():
            if len(modulation_markers(line)) >= 2:
                one_line_hits += 1
        mixed_penalty = min(0.35, one_line_hits * 0.05)
    return max(0.0, recall - mixed_penalty)


def speed_score(s_per_page: float) -> float:
    return 1.0 / (1.0 + math.log10(1.0 + max(0.0, s_per_page)))


def composite(row: dict[str, Any]) -> float:
    weights = {"tca": 0.40, "fls": 0.25, "ss": 0.20, "mmns": 0.15}
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        value = row.get(key)
        if value is None:
            continue
        total += float(value) * weight
        used += weight
    return total / used if used else 0.0


def weighted_mean(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [(float(row[key]), float(row["weight"])) for row in rows if row.get(key) is not None]
    if not vals:
        return None
    weight_sum = sum(weight for _, weight in vals)
    return sum(value * weight for value, weight in vals) / weight_sum


def main() -> None:
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    gt_dir = Path(cfg["ground_truth_dir"])
    output_dir = Path(cfg["output_dir"])
    report_dir = Path(cfg["report_dir"])
    report_dir.mkdir(parents=True, exist_ok=True)

    weights_cfg = cfg.get("evaluation", {}).get("weights", {})
    tier_weights = {
        1: float(weights_cfg.get("tier1", 1.0)),
        2: float(weights_cfg.get("tier2", 1.5)),
        3: float(weights_cfg.get("tier3", 2.0)),
    }
    parsers = [name for name, parser_cfg in cfg.get("parsers", {}).items() if parser_cfg.get("enabled", True)]
    reviewed = load_reviewed_gt(gt_dir)

    detail_rows: list[dict[str, Any]] = []
    for gt_path, gt in reviewed:
        gt_tables = [table for table in gt.get("tables", []) if isinstance(table, dict)]
        for parser in parsers:
            pred_json_path = output_dir / parser / f"{gt_path.stem}.json"
            pred_md_path = output_dir / parser / f"{gt_path.stem}.md"
            if not pred_json_path.exists():
                continue

            try:
                pred_json = json.loads(pred_json_path.read_text(encoding="utf-8"))
            except Exception:
                pred_json = {}
            pred_tables = extract_doc_tables(pred_json)
            pred_full_text = parser_text(pred_json_path, pred_md_path)
            matches = [best_table_match(gt_table, pred_tables) for gt_table in gt_tables]
            match_indices = [idx if score >= 0.20 else -1 for _, idx, score in matches]
            table_tca = [score_tca(gt_table, pred if score >= 0.20 else None) for gt_table, (pred, _, score) in zip(gt_tables, matches)]

            fls_values: list[float] = []
            fls_footnotes = 0
            for gt_table, (pred, _, score) in zip(gt_tables, matches):
                fls, footnote_count = score_fls(gt_table, pred if score >= 0.20 else None, pred_full_text)
                if fls is not None:
                    fls_values.append(fls)
                    fls_footnotes += footnote_count

            row = {
                "parser": parser,
                "pdf": gt_path.stem,
                "tier": int(gt.get("tier", 1)),
                "weight": tier_weights.get(int(gt.get("tier", 1)), 1.0),
                "tables_gt": len(gt_tables),
                "tables_pred": len(pred_tables),
                "footnotes_gt": fls_footnotes,
                "tca": mean(table_tca) if table_tca else 0.0,
                "fls": mean(fls_values) if fls_values else None,
                "ss": score_structure(gt, pred_tables, pred_full_text, match_indices),
                "mmns": score_mmns(gt, pred_full_text),
                "s_per_page": float(pred_json.get("s_per_page", 0.0)) if isinstance(pred_json, dict) else 0.0,
            }
            row["composite"] = composite(row)
            row["speed_score"] = speed_score(row["s_per_page"])
            detail_rows.append(row)

    summary_rows: list[dict[str, Any]] = []
    for parser in parsers:
        rows = [row for row in detail_rows if row["parser"] == parser]
        if not rows:
            continue
        summary = {
            "parser": parser,
            "pdfs_evaluated": len(rows),
            "composite": weighted_mean(rows, "composite"),
            "tca": weighted_mean(rows, "tca"),
            "fls": weighted_mean(rows, "fls"),
            "ss": weighted_mean(rows, "ss"),
            "mmns": weighted_mean(rows, "mmns"),
            "speed_score": mean(row["speed_score"] for row in rows),
            "s_per_page": mean(row["s_per_page"] for row in rows),
        }
        summary_rows.append(summary)
    summary_rows.sort(key=lambda row: row["composite"] or 0.0, reverse=True)

    def rounded(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 4)
        return value

    detail_csv = report_dir / "llm_rescore_reviewed_detail.csv"
    summary_csv = report_dir / "llm_rescore_reviewed_summary.csv"
    json_path = report_dir / "llm_rescore_reviewed.json"

    detail_fields = [
        "parser",
        "pdf",
        "tier",
        "tables_gt",
        "tables_pred",
        "footnotes_gt",
        "tca",
        "fls",
        "ss",
        "mmns",
        "composite",
        "speed_score",
        "s_per_page",
    ]
    with detail_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=detail_fields)
        writer.writeheader()
        for row in detail_rows:
            writer.writerow({field: rounded(row.get(field)) for field in detail_fields})

    summary_fields = ["parser", "pdfs_evaluated", "composite", "tca", "fls", "ss", "mmns", "speed_score", "s_per_page"]
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({field: rounded(row.get(field)) for field in summary_fields})

    json_path.write_text(
        json.dumps(
            {
                "scope": {
                    "reviewed_non_empty_datasheets": [path.stem for path, _ in reviewed],
                    "parser_count": len(parsers),
                    "note": "FLS and MMNS are averaged only where applicable, then composite is reweighted over available KPI components.",
                },
                "summary": [{key: rounded(value) for key, value in row.items()} for row in summary_rows],
                "detail": [{key: rounded(value) for key, value in row.items() if key != "weight"} for row in detail_rows],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Reviewed non-empty datasheets: {len(reviewed)}")
    print(f"Parser outputs scored: {len(detail_rows)}")
    print(f"Saved {summary_csv}")
    print(f"Saved {detail_csv}")
    print(f"Saved {json_path}")
    for row in summary_rows:
        print(
            f"{row['parser']}: composite={row['composite']:.4f} "
            f"tca={row['tca']:.4f} fls={row['fls'] if row['fls'] is not None else 'NA'} "
            f"ss={row['ss']:.4f} mmns={row['mmns'] if row['mmns'] is not None else 'NA'}"
        )


if __name__ == "__main__":
    main()
