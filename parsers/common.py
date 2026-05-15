from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

import yaml


def load_config() -> Dict[str, Any]:
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def list_pdfs(corpus_dir: Path) -> List[Path]:
    return sorted(corpus_dir.glob("*.pdf"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def get_page_count(pdf_path: Path) -> int:
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        pages = doc.page_count
        doc.close()
        return max(1, int(pages))
    except Exception:
        return 1


def run_with_timeout(fn: Callable[[], Any], timeout_s: float) -> Tuple[bool, Any, float, str | None]:
    start = time.perf_counter()
    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(fn)
    try:
        result = fut.result(timeout=max(1.0, timeout_s))
        elapsed = time.perf_counter() - start
        pool.shutdown(wait=True)
        return True, result, elapsed, None
    except FuturesTimeoutError:
        fut.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        elapsed = time.perf_counter() - start
        return False, None, elapsed, "timeout"
    except Exception as exc:  # noqa: BLE001
        pool.shutdown(wait=False, cancel_futures=True)
        elapsed = time.perf_counter() - start
        return False, None, elapsed, f"{type(exc).__name__}: {exc}"


def write_outputs(
    output_dir: Path,
    stem: str,
    json_payload: Dict[str, Any],
    markdown_text: str,
) -> None:
    ensure_dir(output_dir)
    (output_dir / f"{stem}.json").write_text(
        json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / f"{stem}.md").write_text(markdown_text, encoding="utf-8")


def make_error_payload(parser_name: str, pdf_path: Path, pages: int, elapsed: float, error: str) -> Dict[str, Any]:
    return {
        "parser": parser_name,
        "source": str(pdf_path),
        "pages": pages,
        "elapsed_s": round(elapsed, 3),
        "s_per_page": round(elapsed / max(pages, 1), 3),
        "error": error,
        "tables": [],
    }


def extract_markdown_tables(md_text: str) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if "|" in sep and "-" in sep:
                header = [h.strip() for h in line.strip("|").split("|")]
                rows: List[Dict[str, str]] = []
                i += 2
                while i < len(lines) and "|" in lines[i]:
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if len(cells) == len(header):
                        rows.append({header[idx]: cells[idx] for idx in range(len(header))})
                    i += 1
                tables.append(
                    {
                        "title": header[0] if header else "table",
                        "headers": header,
                        "rows": rows,
                        "raw_text": "\n".join([line, sep] + [json.dumps(r) for r in rows]),
                    }
                )
                continue
        i += 1
    return tables
