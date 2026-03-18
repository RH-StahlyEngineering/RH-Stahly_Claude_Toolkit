#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_large",
        description="Find files above a size threshold.",
        epilog=(
            "examples:\n"
            "  python find_large.py 100mb\n"
            "  python find_large.py 1gb --ext zip\n"
            '  python find_large.py 500kb --path "C:\\Users" -n 50\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("size", help="minimum size threshold (e.g. 100mb, 1gb, 500kb)")
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("--ext", default=None, help="filter by file extension")
    parser.add_argument("-n", type=int, default=100, help="max results (default: 100)")
    args = parser.parse_args()

    parts = [f"size:>{args.size}"]
    if args.ext:
        parts.append(f"ext:{args.ext}")
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n, sort="size")
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No files larger than {args.size} found.")
        return

    print(f"Found {len(results)} file(s) larger than {args.size}:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
