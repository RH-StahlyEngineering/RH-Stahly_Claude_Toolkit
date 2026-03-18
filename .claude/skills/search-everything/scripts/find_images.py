#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from es_search import run_query

DEFAULT_IMG_EXT = "jpg;jpeg;png;tif;tiff;bmp;gif;webp"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="find_images",
        description="Find images by properties (dimensions, orientation, extension).",
        epilog=(
            "examples:\n"
            "  python find_images.py\n"
            "  python find_images.py --min-width 1920 --min-height 1080\n"
            "  python find_images.py --orientation landscape --ext jpg;png\n"
            '  python find_images.py --min-width 4000 --path "C:\\Photos"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--min-width", type=int, default=None, help="minimum image width in pixels")
    parser.add_argument("--min-height", type=int, default=None, help="minimum image height in pixels")
    parser.add_argument(
        "--orientation",
        choices=["landscape", "portrait"],
        default=None,
        help="image orientation filter",
    )
    parser.add_argument("--ext", default=DEFAULT_IMG_EXT, help=f"extension filter (default: {DEFAULT_IMG_EXT})")
    parser.add_argument("--path", default=None, help="scope search to a directory")
    parser.add_argument("-n", type=int, default=100, help="max results (default: 100)")
    args = parser.parse_args()

    parts = ["pic:"]
    if args.min_width:
        parts.append(f"width:>{args.min_width}")
    if args.min_height:
        parts.append(f"height:>{args.min_height}")
    if args.orientation:
        parts.append(f"orientation:{args.orientation}")
    ext = args.ext.replace(",", ";").strip(";")
    parts.append(f"ext:{ext}")
    if args.path:
        parts.append(f'path:"{args.path}"')
    query = " ".join(parts)

    try:
        results = run_query(query, max_results=args.n)
    except (FileNotFoundError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not results:
        print("No images found matching criteria.")
        return

    print(f"Found {len(results)} image(s):")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
