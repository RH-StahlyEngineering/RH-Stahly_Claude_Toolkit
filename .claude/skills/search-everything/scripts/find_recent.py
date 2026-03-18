#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query

PRESETS = {"today", "yesterday", "thisweek", "thismonth", "thisyear"}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_recent",
        description="Find recently modified files.",
        epilog=(
            "examples:\n"
            "  python find_recent.py\n"
            "  python find_recent.py --since yesterday --ext py\n"
            "  python find_recent.py --since 2024-01-15\n"
            '  python find_recent.py --since thisweek --path "C:\\Projects"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--since",
        default="today",
        help="time filter: today, yesterday, thisweek, thismonth, thisyear, or a date (default: today)",
    )
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("--ext", default=None, help="filter by file extension")
    parser.add_argument("-n", type=int, default=100, help="max results (default: 100)")
    args = parser.parse_args()

    parts = [f"dm:{args.since}"]
    if args.ext:
        parts.append(f"ext:{args.ext}")
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n, sort="date")
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No files modified since {args.since}.")
        return

    print(f"Found {len(results)} file(s) modified since {args.since}:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
