#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="search_content",
        description="Search inside file contents (requires Everything content indexing; slow).",
        epilog=(
            "examples:\n"
            '  python search_content.py "def main"\n'
            '  python search_content.py "TODO" --ext py\n'
            '  python search_content.py "database" --path "C:\\Projects" -n 20\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("text", help="text to search for inside files")
    parser.add_argument("--ext", default=None, help="filter by file extension")
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("-n", type=int, default=50, help="max results (default: 50)")
    args = parser.parse_args()

    parts = [f'content:"{args.text}"']
    if args.ext:
        parts.append(f"ext:{args.ext}")
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n)
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No files contain '{args.text}'.")
        return

    print(f"Found {len(results)} file(s) containing '{args.text}':")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
