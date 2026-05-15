from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Tuple

from parsers.common import (
    append_jsonl,
    ensure_dir,
    extract_markdown_tables,
    get_page_count,
    list_pdfs,
    load_config,
    make_error_payload,
    run_with_timeout,
    write_outputs,
)


PARSER_NAME = "docling"


def run_one(pdf_path: Path, output_dir: Path, timeout_per_page: float) -> None:
    pages = get_page_count(pdf_path)
    timeout_s = timeout_per_page * pages * 1.5
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, 0.0, "library not installed")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: library not installed")
        return

    converter = DocumentConverter()

    def _convert() -> Tuple[str, Dict[str, Any], int]:
        result = converter.convert(str(pdf_path))
        doc = result.document
        md_text = doc.export_to_markdown()
        doc_dict = doc.export_to_dict()
        doc_pages = len(getattr(doc, "pages", [])) or pages
        return md_text, doc_dict, doc_pages

    ok, output, elapsed, err = run_with_timeout(_convert, timeout_s)
    if not ok:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, elapsed, err or "conversion failed")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: ERROR {payload['error']}")
        return

    md_text, doc_dict, doc_pages = output
    payload: Dict[str, Any] = {
        "parser": PARSER_NAME,
        "source": str(pdf_path),
        "pages": int(doc_pages),
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(1, int(doc_pages)), 3),
        "document": doc_dict,
        "tables": extract_markdown_tables(md_text),
    }
    write_outputs(output_dir, pdf_path.stem, payload, md_text)
    print(f"[{PARSER_NAME}] {pdf_path.name}: {payload['pages']}p in {elapsed:.2f}s ({payload['s_per_page']}s/p)")


def main() -> None:
    cfg = load_config()
    parser_cfg = cfg["parsers"][PARSER_NAME]
    if not parser_cfg.get("enabled", True):
        return

    corpus = Path(cfg["corpus_dir"])
    out_dir = Path(cfg["output_dir"]) / PARSER_NAME
    obs_file = Path(cfg["report_dir"]) / "observability" / "events.jsonl"
    ensure_dir(out_dir)

    for pdf in list_pdfs(corpus):
        t0 = time.perf_counter()
        run_one(pdf, out_dir, float(parser_cfg.get("timeout_per_page", 10)))
        append_jsonl(
            obs_file,
            {
                "ts": time.time(),
                "stage": "parser",
                "parser": PARSER_NAME,
                "pdf": pdf.name,
                "elapsed_s": round(time.perf_counter() - t0, 3),
            },
        )


if __name__ == "__main__":
    main()
