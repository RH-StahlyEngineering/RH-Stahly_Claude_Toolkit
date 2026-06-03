"""make_signature.py -- convert a scanned/photographed ink signature into
a PNG with a transparent background.

Uses an alpha-by-luminance ramp: dark pixels (ink) become opaque, light
pixels (paper) become transparent, with a smooth ramp through the mid-tones
that preserves anti-aliased pen edges. Ink color is preserved by default
(so a blue pen stays blue) -- pass --force-black to recolor strokes to pure
black.

For full photos, color logos, or subjects with both light and dark regions,
this approach is wrong -- use an ML-based tool like `rembg` instead.

USAGE
    python make_signature.py <input.jpg> [--out OUT] [--dark N] [--light N]
                                          [--force-black] [--autocontrast]
                                          [--blur RADIUS]

Defaults:
    --out         <input_dir>/<stem>_transparent.png
    --dark        90   (pixels darker than this go fully opaque)
    --light       230  (pixels lighter than this go fully transparent)
    --blur        0    (Gaussian pre-blur radius; raise to 0.5+ to kill paper-texture speckle)

Tuning (see references/signature_prep.md for the full guide):
    Paper tint still visible -> raise --light (230 -> 240 or 250)
    Thin strokes vanish      -> raise --dark  (90 -> 110 or 120)
    Speckle / noise          -> --blur 0.5
    Uneven phone lighting    -> --autocontrast
    Need pure-black ink      -> --force-black
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Force UTF-8 on Windows so non-ASCII status glyphs (✗ ✓ ⚠ → — etc.) don't
# crash with UnicodeEncodeError on cp1252 consoles.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

try:
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
except ImportError as e:
    print(f"Missing dependency: {e}. Install with `pip install Pillow numpy`.", file=sys.stderr)
    sys.exit(2)


# Rec. 601 perceptual luminance weights. Do not simplify to a plain RGB
# average -- that under-weights green and over-weights blue, which gives
# the wrong alpha for blue ink.
LUM_R, LUM_G, LUM_B = 0.299, 0.587, 0.114


def convert(src: Path, dst: Path, dark: float, light: float,
            force_black: bool, autocontrast: bool, blur: float) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if light <= dark:
        raise ValueError(f"--light ({light}) must be greater than --dark ({dark})")

    pil = Image.open(src).convert("RGB")
    if autocontrast:
        pil = ImageOps.autocontrast(pil)
    if blur > 0:
        pil = pil.filter(ImageFilter.GaussianBlur(radius=blur))

    img = np.asarray(pil, dtype=np.float32)
    lum = LUM_R * img[..., 0] + LUM_G * img[..., 1] + LUM_B * img[..., 2]
    alpha = np.clip((light - lum) / (light - dark), 0.0, 1.0) * 255.0

    rgb = np.zeros_like(img) if force_black else img
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(dst)


def main():
    ap = argparse.ArgumentParser(description="Convert a signature scan to a transparent PNG.")
    ap.add_argument("input", help="Path to the input signature image (JPG/PNG/etc.)")
    ap.add_argument("--out", default=None,
                    help="Output PNG path (default: <input_dir>/<stem>_transparent.png)")
    ap.add_argument("--dark", type=float, default=90.0,
                    help="Luminance at which alpha hits 255 (default: 90)")
    ap.add_argument("--light", type=float, default=230.0,
                    help="Luminance at which alpha hits 0 (default: 230)")
    ap.add_argument("--force-black", action="store_true",
                    help="Recolor strokes to pure black instead of preserving ink color")
    ap.add_argument("--autocontrast", action="store_true",
                    help="Pre-stretch contrast (good for phone photos with uneven lighting)")
    ap.add_argument("--blur", type=float, default=0.0,
                    help="Gaussian pre-blur radius to suppress paper texture (try 0.5)")
    args = ap.parse_args()

    src = Path(args.input)
    if args.out:
        dst = Path(args.out)
    else:
        dst = src.with_name(f"{src.stem}_transparent.png")

    convert(src, dst, args.dark, args.light, args.force_black, args.autocontrast, args.blur)
    print(f"Saved: {dst}")


if __name__ == "__main__":
    main()
