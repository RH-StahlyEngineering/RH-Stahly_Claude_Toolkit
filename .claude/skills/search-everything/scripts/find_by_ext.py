#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_by_ext",
        description="Find files by extension(s).",
        epilog=(
            "examples:\n"
            "  python find_by_ext.py py\n"
            "  python find_by_ext.py py,js,ts\n"
            '  python find_by_ext.py pdf,docx --path "C:\\Documents" -n 50\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "extensions",
        help="comma-separated extensions (e.g. py,js,ts)",
    )
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("-n", type=int, default=100, help="max results (default: 100)")
    args = parser.parse_args()

    ext_list = args.extensions.replace(",", ";").strip(";")
    parts = [f"ext:{ext_list}"]
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n)
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No files found with extension(s): {args.extensions}")
        return

    print(f"Found {len(results)} file(s) with extension(s) {args.extensions}:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
