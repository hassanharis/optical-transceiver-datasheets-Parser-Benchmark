"""
Build corpus/ground_truth/*.json from pymupdf4llm outputs (MD + JSON).

The benchmark scores parsers against these files (see evaluation/ground_truth.py).
Source PDFs live under corpus_dir (config: datasheets); pymupdf4llm was run on
those PDFs, so its markdown tables and headings are used as a silver-standard
extraction aligned with parsers.common.extract_markdown_tables.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.ground_truth import validate_ground_truth


def _section_order_from_md(md: str) -> list[str]:
    headings: list[str] = []
    for line in md.splitlines():
        stripped = line.strip()
        m = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if not m:
            continue
        text = m.group(1).strip()
        text = re.sub(r"\*+", "", text).strip()
        if not text:
            continue
        if text.startswith("==>") and "picture" in text.lower():
            continue
        headings.append(text)
    return headings


def _tier_from_pages(pages: int) -> int:
    if pages <= 4:
        return 1
    if pages <= 10:
        return 2
    return 3


def build_one(stem: str, ref_json: Path, ref_md: Path) -> dict:
    payload = json.loads(ref_json.read_text(encoding="utf-8"))
    md = ref_md.read_text(encoding="utf-8", errors="ignore")
    pages = int(payload.get("pages") or 1)
    source = payload.get("source") or f"datasheets\\{stem}.pdf"

    tables_out: list[dict] = []
    for t in payload.get("tables") or []:
        headers = list(t.get("headers") or [])
        rows = t.get("rows") or []
        title = str(t.get("title") or (headers[0] if headers else "table"))
        tables_out.append(
            {
                "table_id": title,
                "headers": headers,
                "rows": rows,
                "footnotes": {},
            }
        )

    gt = {
        "source": source,
        "tier": _tier_from_pages(pages),
        "tables": tables_out,
        "structure": {
            "section_order": _section_order_from_md(md),
            "total_tables": len(tables_out),
        },
    }
    validate_ground_truth(gt, Path(f"{stem}.json"))
    return gt


def main() -> None:
    root = ROOT
    cfg_path = root / "config.yaml"
    if not cfg_path.exists():
        print(f"Missing {cfg_path}", file=sys.stderr)
        sys.exit(1)

    import yaml

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    gt_dir = root / cfg["ground_truth_dir"]
    ref_dir = root / cfg["output_dir"] / "pymupdf4llm"
    gt_dir.mkdir(parents=True, exist_ok=True)

    if not ref_dir.exists():
        print(f"Missing reference parser output: {ref_dir}", file=sys.stderr)
        sys.exit(1)

    stems = sorted(p.stem for p in ref_dir.glob("*.json"))
    if not stems:
        print(f"No JSON files in {ref_dir}", file=sys.stderr)
        sys.exit(1)

    for stem in stems:
        ref_json = ref_dir / f"{stem}.json"
        ref_md = ref_dir / f"{stem}.md"
        if not ref_md.exists():
            print(f"skip {stem}: missing {ref_md.name}", file=sys.stderr)
            continue
        gt = build_one(stem, ref_json, ref_md)
        out_path = gt_dir / f"{stem}.json"
        out_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
        print(out_path)

    print(f"Wrote {len(stems)} ground truth file(s) under {gt_dir}")


if __name__ == "__main__":
    main()
