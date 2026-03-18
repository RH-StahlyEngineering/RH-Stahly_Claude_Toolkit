#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_empty",
        description="Find empty files or folders.",
        epilog=(
            "examples:\n"
            "  python find_empty.py\n"
            "  python find_empty.py --type files\n"
            '  python find_empty.py --type folders --path "C:\\Projects"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--type",
        choices=["folders", "files"],
        default="folders",
        dest="target_type",
        help="what to search for (default: folders)",
    )
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("-n", type=int, default=100, help="max results (default: 100)")
    args = parser.parse_args()

    if args.target_type == "folders":
        parts = ["folder:", "empty:"]
    else:
        parts = ["file:", "size:0"]
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n)
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No empty {args.target_type} found.")
        return

    print(f"Found {len(results)} empty {args.target_type}:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
