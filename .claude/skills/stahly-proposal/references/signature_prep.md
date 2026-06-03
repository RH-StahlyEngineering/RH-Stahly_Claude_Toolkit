# Preparing a Transparent Signature PNG

`scripts/make_signature.py` converts an ink-on-paper signature scan into a PNG
with a transparent background, using an alpha-by-luminance ramp. Dark pixels
(ink) become opaque, light pixels (paper) become transparent, with a smooth
ramp through the mid-tones that preserves anti-aliased pen edges.

Use this to prep a signatory's signature image (Aaron Kensinger, Rylan Stahly,
etc.) before overlaying it onto a contract, signed proposal, or email
signature block.

## When to use this -- and when not to

**Use it when:** the input is a clean scan or phone photo of dark ink on
light-ish paper. Black ink, blue ink, etc. -- ink color is preserved by
default. Best on scanner output; phone photos work but may need
`--autocontrast`.

**Don't use it when:** the input is a full photo, a color logo, or has both
light and dark regions that matter. The luminance ramp can't distinguish a
dark shadow from dark ink. Use an ML-based tool (`rembg`) instead.

## Quick start

```powershell
python ~/.claude/skills/stahly-proposal/scripts/make_signature.py "C:\path\to\scan.jpg"
# writes C:\path\to\scan_transparent.png
```

Then open the output and check three things:
1. Paper is fully gone -- no faint haze, no rectangle outline.
2. Strokes are intact -- nothing thin has vanished.
3. Edges look clean -- no jaggies, no halo.

If any of those fail, retry with the tuning knobs below.

## Tuning knobs

| Symptom | Fix |
|---|---|
| Paper tint still visible as a faint haze or rectangle | Raise `--light` (230 -> 240 or 250) |
| Thin pen strokes vanish or look broken | Raise `--dark` (90 -> 110 or 120) |
| Speckle / noise / paper-texture grain in the background | `--blur 0.5` |
| Phone photo with uneven lighting | `--autocontrast` (often combine with `--blur 0.5`) |
| Need pure-black ink (e.g., to match printed text) | `--force-black` |
| Result inverted (paper opaque, ink transparent) | Sign isn't dark-on-light -- this tool is wrong for the input |

## Why the luminance formula matters

The script uses Rec. 601 perceptual weights: `0.299*R + 0.587*G + 0.114*B`.
**Don't simplify to a plain RGB average.** A plain average under-weights green
and over-weights blue, which produces visibly wrong alpha for blue ink
(strokes look too transparent at the edges, paper near blue ink doesn't
clear properly). Rec. 601 is the standard perceptual weighting for SDR
imagery and is the right choice here.

## Why a ramp, not a hard threshold

A hard threshold (`alpha = 255 if lum < N else 0`) produces jagged,
aliased edges -- the signature looks like it was cut out with scissors.
The smooth ramp through the mid-tones preserves the anti-aliased pen
edges that scanners produce, giving clean curves when the PNG is
overlaid on white or off-white backgrounds.

## Where to put the output

For Stahly proposals, signatures will eventually live alongside the official
logos in `assets/signatures/` and be wired into the signature block by file
path. That wiring isn't in v1.1 yet -- for now, save the transparent PNG
wherever the user wants and overlay it manually in the final PDF (or in
Word, if signing a docx draft).
