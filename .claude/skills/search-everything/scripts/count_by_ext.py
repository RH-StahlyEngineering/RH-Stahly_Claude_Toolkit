#!/usr/bin/env python3
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="count_by_ext",
        description="Count files grouped by extension in a path.",
        epilog=(
            "examples:\n"
            '  python count_by_ext.py "C:\\Projects\\myapp"\n'
            '  python count_by_ext.py "C:\\Users\\me\\Documents" --top 10\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", help="directory path to scan")
    parser.add_argument("--top", type=int, default=20, help="show top N extensions (default: 20)")
    args = parser.parse_args()

    query = f'path:"{args.path}" file:'

    try:
        results = run_query(query, max_results=50000)
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No files found in {args.path}")
        return

    counts: Counter[str] = Counter()
    for filepath in results:
        suffix = Path(filepath).suffix.lower()
        counts[suffix if suffix else "(no ext)"] += 1

    ranked = counts.most_common(args.top)
    max_ext_len = max(len(ext) for ext, _ in ranked)
    max_count_len = max(len(str(c)) for _, c in ranked)

    print(f"Top {min(args.top, len(ranked))} extensions in {args.path} ({len(results)} files):\n")
    for ext, count in ranked:
        print(f"  {ext:<{max_ext_len}}  {count:>{max_count_len}}")


if __name__ == "__main__":
    main()
