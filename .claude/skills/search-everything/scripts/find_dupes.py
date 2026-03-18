#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query

DUPE_MAP = {
    "name": "dupe:",
    "size": "sizedupe:",
    "datemodified": "dmdupe:",
    "datecreated": "dcdupe:",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_dupes",
        description="Find duplicate files by name, size, or date.",
        epilog=(
            "examples:\n"
            "  python find_dupes.py\n"
            "  python find_dupes.py --by size --ext pdf\n"
            '  python find_dupes.py --by name --path "C:\\Projects" -n 50\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--by",
        choices=list(DUPE_MAP),
        default="name",
        help="duplicate detection method (default: name)",
    )
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("--ext", default=None, help="filter by file extension (e.g. pdf)")
    parser.add_argument("-n", type=int, default=200, help="max results (default: 200)")
    args = parser.parse_args()

    parts = [DUPE_MAP[args.by]]
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
        print("No duplicates found.")
        return

    print(f"Found {len(results)} duplicate(s):")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
