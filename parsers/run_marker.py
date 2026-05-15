from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from parsers.common import (
    append_jsonl,
    ensure_dir,
    extract_markdown_tables,
    get_page_count,
    list_pdfs,
    load_config,
    make_error_payload,
    write_outputs,
)


PARSER_NAME = "marker"


def resolve_marker_single() -> str | None:
    scripts_dir = Path(sys.executable).parent
    candidates = [scripts_dir / "marker_single.exe", scripts_dir / "marker_single"]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("marker_single")


def run_one(pdf_path: Path, output_dir: Path, timeout_per_page: float) -> None:
    pages = get_page_count(pdf_path)
    timeout_s = max(1.0, timeout_per_page * pages * 1.5)
    marker_single = resolve_marker_single()
    if not marker_single:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, 0.0, "library not installed")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: library not installed")
        return

    tmp_out = output_dir / "_marker_tmp"
    ensure_dir(tmp_out)
    cmd = [
        marker_single,
        str(pdf_path),
        "--output_format",
        "markdown",
        "--output_dir",
        str(tmp_out),
        "--disable_tqdm",
    ]

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        elapsed = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, timeout_s, "timeout")
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: ERROR timeout")
        return

    out_subdir = tmp_out / pdf_path.stem
    md_file = out_subdir / f"{pdf_path.stem}.md"
    if not md_file.exists():
        err_text = (proc.stderr or proc.stdout or "marker conversion failed").strip()
        if len(err_text) > 400:
            err_text = err_text[:400]
        payload = make_error_payload(PARSER_NAME, pdf_path, pages, elapsed, err_text)
        write_outputs(output_dir, pdf_path.stem, payload, "")
        print(f"[{PARSER_NAME}] {pdf_path.name}: ERROR {payload['error']}")
        return

    md_text = md_file.read_text(encoding="utf-8", errors="ignore")
    payload: Dict[str, Any] = {
        "parser": PARSER_NAME,
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(1, pages), 3),
        "tables": extract_markdown_tables(md_text),
    }
    write_outputs(output_dir, pdf_path.stem, payload, md_text)
    print(f"[{PARSER_NAME}] {pdf_path.name}: {pages}p in {elapsed:.2f}s ({payload['s_per_page']}s/p)")


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
        run_one(pdf, out_dir, float(parser_cfg.get("timeout_per_page", 120)))
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
