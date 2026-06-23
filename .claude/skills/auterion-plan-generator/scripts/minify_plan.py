"""
Normalize a .plan file to the controller-compatible format.

The Auterion RC controller's JSON parser rejects pretty-printed JSON with CRLF
line endings. Desktop AMC reads either, but writes pretty-printed CRLF.
This script normalizes to: minified, LF only, UTF-8, no BOM.

Usage:
    python minify_plan.py input.plan [output.plan]
    python minify_plan.py *.plan        # batch, writes alongside with _rc.plan suffix
"""
import glob
import json
import os
import sys


def minify(src: str, dst: str = None) -> str:
    """Read .plan from src, write minified version to dst (default = src with _rc.plan suffix).

    Returns the destination path.
    """
    if dst is None:
        dst = src[:-5] + '_rc.plan' if src.endswith('.plan') else src + '.minified'
    with open(src, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 'wb' is critical — text mode on Windows injects CR
    with open(dst, 'wb') as f:
        f.write(json.dumps(data, separators=(',', ':')).encode('utf-8'))
    return dst


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]
    # Single-file form: input.plan output.plan
    if len(args) == 2 and not any(c in args[0] for c in '*?[') and not args[1].endswith('.plan') is False:
        # both args look like real paths and second isn't a glob → write to args[1]
        if os.path.isfile(args[0]) and not any(c in args[1] for c in '*?['):
            out = minify(args[0], args[1])
            print(f"{args[0]} -> {out}")
            return

    # Batch / glob form
    paths = []
    for a in args:
        paths.extend(glob.glob(a) or [a])
    for p in paths:
        if not os.path.isfile(p):
            print(f"SKIP (not a file): {p}")
            continue
        try:
            out = minify(p)
            print(f"{p} ({os.path.getsize(p)} B) -> {out} ({os.path.getsize(out)} B)")
        except Exception as e:
            print(f"ERROR {p}: {e}")


if __name__ == '__main__':
    main()
