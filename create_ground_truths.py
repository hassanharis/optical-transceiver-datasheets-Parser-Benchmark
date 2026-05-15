#!/usr/bin/env python3
"""Generate editable ground truth JSON drafts from parser outputs."""

from __future__ import annotations

import html
import json
import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List

import yaml

TITLE_TYPES = {"Title", "Header"}
TEXT_TYPES = {"Text", "NarrativeText", "ListItem", "Title"}
FOOTNOTE_RE = re.compile(r"^\s*(\d{1,2})\s*[).]\s+(.+)")
MODULATION_RE = re.compile(r"\b(dp-?qpsk|dqpsk|qpsk|bpsk|pam4|8-?qam|16-?qam|64-?qam|coherent)\b", re.I)
TABLE_SOURCE_ORDER = ["unstructured_hires", "marker", "docling", "pymupdf4llm"]
SKIP_SECTION_VALUES = {
    "DATASHEET",
    "SMARTOPTICS",
    "PROLABS",
    "FLUXLIGHT, INC.",
}


class SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[Dict[str, Any]]] = []
        self.current_row: List[Dict[str, Any]] | None = None
        self.current_cell: Dict[str, Any] | None = None
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.in_cell = True
            self.current_cell = {
                "text": "",
                "is_header": tag == "th",
                "rowspan": _safe_int(attrs_dict.get("rowspan"), 1),
                "colspan": _safe_int(attrs_dict.get("colspan"), 1),
            }

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.current_cell is not None:
            self.current_cell["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current_row is not None and self.current_cell is not None:
            self.current_cell["text"] = clean_text(self.current_cell["text"])
            self.current_row.append(self.current_cell)
            self.current_cell = None
            self.in_cell = False
        elif tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None


def _safe_int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value or default))
    except ValueError:
        return default


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def load_config() -> Dict[str, Any]:
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def get_page_count(pdf_path: Path) -> int:
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        pages = doc.page_count
        doc.close()
        return max(1, int(pages))
    except Exception:
        return 1


def expand_rows(raw_rows: List[List[Dict[str, Any]]]) -> List[List[str]]:
    grid: List[List[str]] = []
    spans: Dict[int, Dict[str, Any]] = {}

    for raw_row in raw_rows:
        row: List[str] = []
        col = 0

        while col in spans:
            row.append(spans[col]["text"])
            spans[col]["remaining"] -= 1
            if spans[col]["remaining"] <= 0:
                del spans[col]
            col += 1

        for cell in raw_row:
            while col in spans:
                row.append(spans[col]["text"])
                spans[col]["remaining"] -= 1
                if spans[col]["remaining"] <= 0:
                    del spans[col]
                col += 1

            text = clean_text(cell.get("text"))
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            for offset in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[col + offset] = {"text": text, "remaining": rowspan - 1}
            col += colspan

        grid.append(row)

    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid if any(cell for cell in row)]


def unique_headers(headers: List[str]) -> List[str]:
    result: List[str] = []
    seen: Dict[str, int] = {}
    for index, header in enumerate(headers):
        name = clean_text(header) or f"Column {index + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name} {count + 1}")
    return result


def parse_html_table(html_text: str) -> tuple[List[str], List[Dict[str, str]]]:
    parser = SimpleTableParser()
    parser.feed(html_text or "")
    grid = expand_rows(parser.rows)
    if not grid:
        return [], []

    first_row_is_header = any(cell.get("is_header") for cell in (parser.rows[0] if parser.rows else []))
    if first_row_is_header or len(grid) > 1:
        headers = unique_headers(grid[0])
        data_rows = grid[1:]
    else:
        headers = unique_headers([f"Column {idx + 1}" for idx in range(len(grid[0]))])
        data_rows = grid

    rows: List[Dict[str, str]] = []
    for row in data_rows:
        if not any(clean_text(cell) for cell in row):
            continue
        rows.append({headers[idx]: clean_text(row[idx]) if idx < len(row) else "" for idx in range(len(headers))})
    return headers, rows


def preceding_title(elements: List[Dict[str, Any]], index: int, fallback: str) -> str:
    for previous in reversed(elements[max(0, index - 8):index]):
        text = clean_text(previous.get("text"))
        if previous.get("type") in TITLE_TYPES and is_section_heading(text):
            return text
    return fallback


def collect_following_footnotes(elements: List[Dict[str, Any]], index: int) -> Dict[str, str]:
    footnotes: Dict[str, str] = {}
    for element in elements[index + 1:index + 12]:
        if element.get("type") == "Table":
            break
        text = clean_text(element.get("text"))
        match = FOOTNOTE_RE.match(text)
        if match:
            footnotes[match.group(1)] = match.group(2)
    return footnotes


def is_section_heading(text: str) -> bool:
    if not text or len(text) < 3:
        return False
    normalized = text.strip().upper()
    if normalized in SKIP_SECTION_VALUES:
        return False
    if FOOTNOTE_RE.match(text):
        return False
    if len(text) > 90:
        return False
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return uppercase_ratio >= 0.72 or text.startswith("#")


def extract_sections(elements: List[Dict[str, Any]]) -> List[str]:
    sections: List[str] = []
    for element in elements:
        text = clean_text(element.get("text"))
        if element.get("type") in TITLE_TYPES and is_section_heading(text):
            sections.append(text)
    return list(dict.fromkeys(sections))


def extract_tables(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    for index, element in enumerate(elements):
        if element.get("type") != "Table":
            continue
        headers, rows = parse_html_table(str(element.get("html") or ""))
        if not rows:
            text = clean_text(element.get("text"))
            headers = ["Text"]
            rows = [{"Text": text}] if text else []
        if not rows:
            continue

        table_number = len(tables) + 1
        title = preceding_title(elements, index, f"Table {table_number}")
        table_id = f"{table_number:02d}_{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_') or 'table'}"
        tables.append(
            {
                "table_id": table_id,
                "title": title,
                "page": element.get("page"),
                "headers": headers,
                "rows": rows,
                "footnotes": collect_following_footnotes(elements, index),
                "needs_review": True,
                "draft_source_parser": "unstructured_hires",
            }
        )
    return tables


def normalize_json_tables(raw_tables: List[Dict[str, Any]], source_parser: str) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    for raw_table in raw_tables:
        headers = unique_headers([clean_text(header) for header in raw_table.get("headers", [])])
        raw_rows = raw_table.get("rows", [])
        if not headers or not isinstance(raw_rows, list):
            continue

        rows: List[Dict[str, str]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            row = {header: clean_text(raw_row.get(header, "")) for header in headers}
            if any(row.values()):
                rows.append(row)
        if not rows:
            continue

        table_number = len(tables) + 1
        title = clean_text(raw_table.get("title")) or f"Table {table_number}"
        table_id = f"{table_number:02d}_{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_') or 'table'}"
        tables.append(
            {
                "table_id": table_id,
                "title": title,
                "headers": headers,
                "rows": rows,
                "footnotes": {},
                "needs_review": True,
                "draft_source_parser": source_parser,
            }
        )
    return tables


def load_parser_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def table_signature(table: Dict[str, Any]) -> str:
    row_text = " ".join(
        " ".join(clean_text(value) for value in row.values())
        for row in table.get("rows", [])[:8]
        if isinstance(row, dict)
    )
    return clean_text(f"{table.get('title', '')} {' '.join(table.get('headers', []))} {row_text}").lower()


def signature_tokens(signature: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", signature.lower()) if len(token) > 1}


def is_duplicate_table(candidate: Dict[str, Any], existing_tables: List[Dict[str, Any]]) -> bool:
    candidate_sig = table_signature(candidate)
    if not candidate_sig:
        return True
    candidate_tokens = signature_tokens(candidate_sig)
    for existing in existing_tables:
        existing_sig = table_signature(existing)
        if not existing_sig:
            continue
        existing_tokens = signature_tokens(existing_sig)
        if candidate_tokens and existing_tokens:
            overlap = len(candidate_tokens & existing_tokens) / max(1, min(len(candidate_tokens), len(existing_tokens)))
            if overlap >= 0.58:
                return True
        if SequenceMatcher(None, candidate_sig, existing_sig).ratio() >= 0.72:
            return True
    return False


def renumber_tables(tables: List[Dict[str, Any]]) -> None:
    for index, table in enumerate(tables, start=1):
        title = clean_text(table.get("title")) or f"Table {index}"
        table["table_id"] = f"{index:02d}_{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_') or 'table'}"


def choose_table_draft(stem: str, output_dir: Path, hires_tables: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    merged_tables = list(hires_tables)
    for parser_name in TABLE_SOURCE_ORDER[1:]:
        data = load_parser_json(output_dir / parser_name / f"{stem}.json")
        raw_tables = data.get("tables", []) if isinstance(data, dict) else []
        if isinstance(raw_tables, list):
            for table in normalize_json_tables(raw_tables, parser_name):
                if not is_duplicate_table(table, merged_tables):
                    merged_tables.append(table)

    renumber_tables(merged_tables)
    source_label = "unstructured_hires" if len(merged_tables) == len(hires_tables) else "merged_unstructured_hires_marker_docling_pymupdf4llm"
    return source_label, merged_tables


def estimate_tier(page_count: int, table_count: int) -> int:
    if page_count <= 3 and table_count <= 4:
        return 1
    if page_count <= 10 and table_count <= 10:
        return 2
    return 3


def create_ground_truth(pdf_path: Path, parser_json_path: Path, parser_md_path: Path, output_dir: Path) -> Dict[str, Any]:
    parsed = json.loads(parser_json_path.read_text(encoding="utf-8"))
    elements = parsed.get("elements", []) if isinstance(parsed, dict) else []
    md_text = parser_md_path.read_text(encoding="utf-8", errors="ignore") if parser_md_path.exists() else ""
    full_text = "\n".join(clean_text(element.get("text")) for element in elements) + "\n" + md_text
    hires_tables = extract_tables(elements)
    table_source, tables = choose_table_draft(pdf_path.stem, output_dir, hires_tables)
    sections = extract_sections(elements)
    page_count = get_page_count(pdf_path)

    return {
        "source": pdf_path.name,
        "page_count": page_count,
        "tier": estimate_tier(page_count, len(tables)),
        "tables": tables,
        "structure": {
            "section_order": sections,
            "total_tables": len(tables),
            "total_footnotes": sum(len(table.get("footnotes", {})) for table in tables),
            "modulation_block": bool(MODULATION_RE.search(full_text)),
        },
        "draft_metadata": {
            "status": "vlm_ocr_candidate_needs_human_review",
            "source_parser": table_source,
            "section_source_parser": "unstructured_hires",
            "notes": "Generated from visual/OCR parser elements and HTML table geometry. Correct against the PDF before final scoring.",
        },
    }


def main() -> None:
    config = load_config()
    corpus_dir = Path(config.get("corpus_dir", "datasheets"))
    output_dir = Path(config.get("output_dir", "outputs"))
    gt_dir = Path(config.get("ground_truth_dir", "corpus/ground_truth"))
    parser_dir = output_dir / "unstructured_hires"
    gt_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    pdfs = sorted(corpus_dir.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")

    for pdf_path in pdfs:
        stem = pdf_path.stem
        parser_json_path = parser_dir / f"{stem}.json"
        parser_md_path = parser_dir / f"{stem}.md"
        gt_path = gt_dir / f"{stem}.json"

        if not parser_json_path.exists():
            print(f"SKIP {stem} (no parser JSON)")
            skipped += 1
            continue

        try:
            gt = create_ground_truth(pdf_path, parser_json_path, parser_md_path, output_dir)
            gt_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
            print(
                f"WRITE {stem} "
                f"(tier={gt['tier']}, tables={gt['structure']['total_tables']}, "
                f"footnotes={gt['structure']['total_footnotes']}, pages={gt['page_count']})"
            )
            created += 1
        except Exception as exc:
            print(f"ERROR {stem}: {type(exc).__name__}: {exc}")
            skipped += 1

    print(f"\nSummary: Wrote {created}, Skipped {skipped}/{len(pdfs)}")


if __name__ == "__main__":
    main()
