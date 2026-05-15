from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

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


PARSER_NAME = "unstructured_fast"


def run_one(pdf_path: Path, output_dir: Path, timeout_per_page: float) -> None:
    pages = get_page_count(pdf_path)
    timeout_s = timeout_per_page * pages * 1.5
    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, 0.0, "library not installed")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: library not installed")
        return

    def _convert() -> List[Any]:
        return partition_pdf(filename=str(pdf_path), strategy="fast")

    ok, elements, elapsed, err = run_with_timeout(_convert, timeout_s)
    if not ok:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, elapsed, err or "conversion failed")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: ERROR {payload['error']}")
        return

    elements = elements or []
    serialized = []
    md_parts = []
    for e in elements:
        text = getattr(e, "text", "") or ""
        meta = getattr(e, "metadata", None)
        html = getattr(meta, "text_as_html", None) if meta is not None else None
        page = getattr(meta, "page_number", None) if meta is not None else None
        etype = type(e).__name__
        serialized.append({"type": etype, "text": text, "html": html, "page": page})
        md_parts.append(html or text)

    md_text = "\n\n".join(x for x in md_parts if x)
    payload: Dict[str, Any] = {
        "parser": PARSER_NAME,
        "source": str(pdf_path),
        "pages": max([pages] + [int(s.get("page") or 1) for s in serialized]),
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(1, pages), 3),
        "elements": serialized,
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
        run_one(pdf, out_dir, float(parser_cfg.get("timeout_per_page", 5)))
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
