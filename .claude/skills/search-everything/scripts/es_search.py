#!/usr/bin/env python3
"""Everything Search CLI wrapper -- thin bridge to voidtools es.exe."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["find_es_exe", "run_query"]

_COMMON_LOCATIONS: list[Path] = [
    Path(r"C:\Program Files\Everything\es.exe"),
    Path(r"C:\Program Files (x86)\Everything\es.exe"),
    Path(r"C:\Program Files\Everything 1.5a\es.exe"),
]

_SORT_MAP: dict[str, str] = {
    "name": "name",
    "path": "path",
    "size": "size",
    "date": "date-modified",
}

_DOWNLOAD_URL = "https://www.voidtools.com/downloads/"


def find_es_exe() -> Path | None:
    on_path = shutil.which("es")
    if on_path:
        return Path(on_path)
    for candidate in _COMMON_LOCATIONS:
        if candidate.is_file():
            return candidate
    return None


def run_query(
    query: str,
    max_results: int = 100,
    sort: str = "name",
    path_scope: str | None = None,
) -> list[str]:
    es = find_es_exe()
    if es is None:
        raise FileNotFoundError(
            f"es.exe not found on PATH or in common locations. "
            f"Download Everything from {_DOWNLOAD_URL}"
        )

    sort_flag = _SORT_MAP.get(sort)
    if sort_flag is None:
        raise ValueError(f"Invalid sort key '{sort}': choose from {list(_SORT_MAP)}")

    cmd: list[str] = [
        str(es),
        "-n", str(max_results),
        "-sort", sort_flag,
    ]

    if path_scope:
        cmd.extend(["-path", path_scope])

    cmd.append(query)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        msg = result.stderr.strip() or f"es.exe exited with code {result.returncode}"
        raise RuntimeError(msg)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="es_search",
        description="Search files using voidtools Everything (es.exe).",
        epilog=(
            "examples:\n"
            '  python es_search.py "*.psx"\n'
            '  python es_search.py -n 20 -s date "report*.pdf"\n'
            '  python es_search.py --path "C:\\Projects" "*.py"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="Everything search query string")
    parser.add_argument(
        "-n", "--max-results",
        type=int,
        default=100,
        help="maximum number of results (default: 100)",
    )
    parser.add_argument(
        "-s", "--sort",
        choices=list(_SORT_MAP),
        default="name",
        help="sort order (default: name)",
    )
    parser.add_argument(
        "--path",
        dest="path_scope",
        default=None,
        help="scope search to a path prefix",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        results = run_query(
            args.query,
            max_results=args.max_results,
            sort=args.sort,
            path_scope=args.path_scope,
        )
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.exit(2)

    for line in results:
        print(line)


if __name__ == "__main__":
    main()
