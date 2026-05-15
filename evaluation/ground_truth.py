from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


REQUIRED_ROOT_FIELDS = {"source", "tier", "tables", "structure"}
REQUIRED_TABLE_FIELDS = {"table_id", "headers", "rows"}


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_ground_truth(data: Dict[str, Any], source_path: Path) -> None:
    missing = REQUIRED_ROOT_FIELDS - set(data.keys())
    _assert(not missing, f"{source_path.name}: missing root fields: {sorted(missing)}")
    _assert(isinstance(data["tier"], int), f"{source_path.name}: tier must be int")
    _assert(isinstance(data["tables"], list), f"{source_path.name}: tables must be list")
    _assert(isinstance(data["structure"], dict), f"{source_path.name}: structure must be object")

    for idx, table in enumerate(data["tables"]):
        _assert(isinstance(table, dict), f"{source_path.name}: tables[{idx}] must be object")
        missing_table = REQUIRED_TABLE_FIELDS - set(table.keys())
        _assert(
            not missing_table,
            f"{source_path.name}: tables[{idx}] missing fields: {sorted(missing_table)}",
        )
        _assert(isinstance(table["headers"], list), f"{source_path.name}: tables[{idx}].headers must be list")
        _assert(isinstance(table["rows"], list), f"{source_path.name}: tables[{idx}].rows must be list")

    section_order = data["structure"].get("section_order", [])
    _assert(isinstance(section_order, list), f"{source_path.name}: structure.section_order must be list")


def load_ground_truth_file(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_ground_truth(data, path)
    return data


def load_ground_truth_dir(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for gt_file in sorted(path.glob("*.json")):
        entries.append(load_ground_truth_file(gt_file))
    return entries
