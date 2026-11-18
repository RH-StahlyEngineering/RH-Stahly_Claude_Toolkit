"""
Closure-report PDF builder. Called by closure_report.ps1.

Reads a JSON file written by the PowerShell wrapper (one entry per parcel with
vertex coords + POB strategy), reorders vertices per the POB strategy,
computes rounded-then-re-inversed closure, and emits a vanilla
AutoCAD/Civil 3D MAPCHECK-style text report rendered to PDF in Courier
monospace. No graphics, no styled headers, no cover page.

Usage:
    python build_closure_report.py <input.json> <output.pdf>
"""
import json
import math
import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


# ---------------------------------------------------------------------------
# Bearing / closure math (rounded to nearest second before computing)
# ---------------------------------------------------------------------------
def fmt_bearing(dx, dy):
    """Return MAPCHECK-style bearing 'N DD-MM-SS W' (hyphenated DMS) plus
    unit-vector components (ux, uy) derived from the rounded bearing."""
    adx, ady = abs(dx), abs(dy)
    if adx < 1e-12 and ady < 1e-12:
        return ("N 00-00-00 E", 1.0, 0.0)
    rad = math.atan2(adx, ady)
    deg = math.degrees(rad)
    total_sec = round(deg * 3600.0)
    d, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    ns = "N" if dy >= 0 else "S"
    ew = "E" if dx >= 0 else "W"
    bearing_str = f"{ns} {int(d):02d}-{int(m):02d}-{int(s):02d} {ew}"
    rounded_deg = total_sec / 3600.0
    rounded_rad = math.radians(rounded_deg)
    abs_ux = math.sin(rounded_rad)
    abs_uy = math.cos(rounded_rad)
    ux = abs_ux if ew == "E" else -abs_ux
    uy = abs_uy if ns == "N" else -abs_uy
    return (bearing_str, ux, uy)


def fmt_misclose_bearing(dx, dy):
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return "N 00-00-00 E"
    return fmt_bearing(dx, dy)[0]


def compute_closure(verts):
    n = len(verts)
    courses = []
    perim = 0.0
    raw_two_a = 0.0
    for i in range(n):
        ax, ay = verts[i]
        bx, by = verts[(i + 1) % n]
        dx = bx - ax
        dy = by - ay
        raw_two_a += ax * by - bx * ay
        bearing_str, ux, uy = fmt_bearing(dx, dy)
        rd = round(math.hypot(dx, dy), 2)
        perim += rd
        courses.append({
            "idx": i + 1,
            "bearing": bearing_str,
            "dist": rd,
            "ux": ux,
            "uy": uy,
            "start": (ax, ay),
        })
    # Re-inverse using rounded values to get the end coordinates the report
    # actually carries, and the misclose to the POB.
    cx, cy = verts[0]
    end_coords = []
    for c in courses:
        cx += c["ux"] * c["dist"]
        cy += c["uy"] * c["dist"]
        end_coords.append((cx, cy))
    mE = cx - verts[0][0]
    mN = cy - verts[0][1]
    err = math.hypot(mE, mN)
    precision = (perim / err) if err > 1e-9 else float("inf")
    err_brg = fmt_misclose_bearing(mE, mN)
    raw_area = abs(raw_two_a) / 2.0
    return {
        "courses": courses,
        "end_coords": end_coords,
        "perimeter": perim,
        "raw_area": raw_area,
        "misclose_N": mN,
        "misclose_E": mE,
        "err_dist": err,
        "err_bearing": err_brg,
        "precision": precision,
    }


# ---------------------------------------------------------------------------
# POB reordering (unchanged from earlier version)
# ---------------------------------------------------------------------------
def rotate(arr, start):
    return arr[start:] + arr[:start]


def apply_pob(verts, strategy, pob_x=None, pob_y=None, first_leg=None):
    if strategy == "AsIs":
        return list(verts)
    if strategy == "Vertex":
        if pob_x is None or pob_y is None:
            raise ValueError("Vertex POB strategy requires POBX, POBY")
        idx = min(range(len(verts)),
                  key=lambda i: math.hypot(verts[i][0] - pob_x,
                                           verts[i][1] - pob_y))
    else:
        if "-" not in strategy:
            raise ValueError(f"Unknown POB strategy: {strategy}")
        corner, first_leg_local = strategy.split("-", 1)
        first_leg = first_leg or first_leg_local
        score_fns = {
            "NE": lambda v: v[0] + v[1],
            "NW": lambda v: -v[0] + v[1],
            "SE": lambda v: v[0] - v[1],
            "SW": lambda v: -v[0] - v[1],
            "N":  lambda v: v[1],
            "S":  lambda v: -v[1],
            "E":  lambda v: v[0],
            "W":  lambda v: -v[0],
        }
        if corner not in score_fns:
            raise ValueError(f"Unknown POB corner: {corner}")
        idx = max(range(len(verts)), key=lambda i: score_fns[corner](verts[i]))

    def dir_matches(a, b, leg):
        dx, dy = b[0] - a[0], b[1] - a[1]
        leg = leg.upper()
        return {
            "N":  dy > 0,
            "S":  dy < 0,
            "E":  dx > 0,
            "W":  dx < 0,
            "NE": dx > 0 and dy > 0,
            "NW": dx < 0 and dy > 0,
            "SE": dx > 0 and dy < 0,
            "SW": dx < 0 and dy < 0,
        }.get(leg, True)

    if first_leg:
        fwd = verts[(idx + 1) % len(verts)]
        bck = verts[(idx - 1) % len(verts)]
        fwd_ok = dir_matches(verts[idx], fwd, first_leg)
        bck_ok = dir_matches(verts[idx], bck, first_leg)
        if (not fwd_ok) and bck_ok:
            v2 = list(reversed(verts))
            new_start = (len(verts) - 1) - idx
            return rotate(v2, new_start)
        if fwd_ok and bck_ok:
            tokens = {
                "N":  lambda v: v[1] - verts[idx][1],
                "S":  lambda v: verts[idx][1] - v[1],
                "E":  lambda v: v[0] - verts[idx][0],
                "W":  lambda v: verts[idx][0] - v[0],
            }
            base_leg = first_leg[0].upper()
            if base_leg in tokens:
                if tokens[base_leg](bck) > tokens[base_leg](fwd):
                    v2 = list(reversed(verts))
                    new_start = (len(verts) - 1) - idx
                    return rotate(v2, new_start)
    return rotate(verts, idx)


# ---------------------------------------------------------------------------
# MAPCHECK text format
# ---------------------------------------------------------------------------
SEP = "-" * 73  # canonical Civil 3D dashed separator width


def fmt_coord(v):
    """Coordinate to 4 decimal places (no thousands separator)."""
    return f"{v:.4f}"


def fmt_dist(v):
    """Distance to 2 decimal places."""
    return f"{v:.2f}"


def fmt_area_sqft(v):
    """Square footage with thousands separator, no decimals."""
    return f"{v:,.0f}"


def fmt_area_ac(v):
    """Acres to 2 decimals with comma thousands."""
    return f"{v:,.2f}"


def fmt_precision(perim, err):
    """Format as `1: N.NNN` where N is comma-thousands-separated."""
    if err < 1e-9:
        return "Precision  1: PERFECT"
    ratio = perim / err
    return f"Precision  1: {ratio:,.3f}"


def parse_verts(parcel):
    """The PowerShell wrapper writes Verts as a flat array [x0,y0,x1,y1,...].
    Earlier callers may pass a list of [x,y] pairs instead. Handle both."""
    raw = parcel.get("Verts") or parcel.get("verts") or []
    if not raw:
        return []
    if isinstance(raw[0], (list, tuple)):
        return [(float(p[0]), float(p[1])) for p in raw]
    # Flat array
    if len(raw) % 2 != 0:
        raise ValueError("Verts array length must be even")
    return [(float(raw[2 * i]), float(raw[2 * i + 1])) for i in range(len(raw) // 2)]


def render_parcel_text(parcel):
    """Render one parcel as MAPCHECK lines."""
    lines = []
    name = parcel.get("Name") or parcel.get("name") or "Parcel"

    # Reorder vertices per POB strategy
    verts_raw = parse_verts(parcel)
    verts = apply_pob(
        verts_raw,
        parcel.get("POBStrategy", "AsIs"),
        parcel.get("POBX"),
        parcel.get("POBY"),
        parcel.get("FirstLeg"),
    )
    result = compute_closure(verts)

    # Parcel header
    lines.append(f"Parcel name: {name}")
    lines.append("")  # blank line per Civil 3D convention

    # POB coordinates (unprefixed; Civil 3D omits the "POB" label)
    pob_x, pob_y = verts[0]
    lines.append(f"   North: {fmt_coord(pob_y)}             East : {fmt_coord(pob_x)}")

    # Each course: two lines (course header + end-vertex coords)
    for i, c in enumerate(result["courses"]):
        end_x, end_y = result["end_coords"][i]
        lines.append(
            f"Line  Course: {c['bearing']}  Length: {fmt_dist(c['dist'])}"
        )
        lines.append(
            f"        North: {fmt_coord(end_y)}             East : {fmt_coord(end_x)}"
        )

    # Closure summary
    lines.append("")
    perim_str = fmt_dist(result["perimeter"])
    area_sqft = result["raw_area"]
    area_ac = area_sqft / 43560.0
    lines.append(
        f"   Perimeter: {perim_str}   Area: {fmt_area_sqft(area_sqft)} Sq Ft  {fmt_area_ac(area_ac)} Ac."
    )
    lines.append("Mapcheck Closure - (Uses listed courses, radii, and deltas)")
    lines.append(
        f"Error Closure: {fmt_dist(result['err_dist'])}                Course: {result['err_bearing']}"
    )
    # Error north/east: signed, 4 decimals (these are tiny so we show all)
    lines.append(
        f"  Error North: {result['misclose_N']:.4f}                East : {result['misclose_E']:.4f}"
    )
    lines.append(fmt_precision(result["perimeter"], result["err_dist"]))
    return lines


# ---------------------------------------------------------------------------
# PDF rendering: pure monospace text
# ---------------------------------------------------------------------------
def render_pdf(all_lines, out_pdf):
    """Render the lines to PDF in Courier. Letter, portrait, ~1/2 inch margins.
    Wraps to new pages when the page is full."""
    page_w, page_h = LETTER
    margin_x = 0.5 * inch
    margin_top = 0.5 * inch
    margin_bot = 0.5 * inch
    font = "Courier"
    font_size = 9
    line_height = 11  # points; tight enough to fit a full parcel per page typical

    c = canvas.Canvas(str(out_pdf), pagesize=LETTER)
    c.setFont(font, font_size)

    y = page_h - margin_top
    x = margin_x
    lines_per_page = int((page_h - margin_top - margin_bot) / line_height)
    line_count = 0

    for line in all_lines:
        if line_count >= lines_per_page:
            c.showPage()
            c.setFont(font, font_size)
            y = page_h - margin_top
            line_count = 0
        c.drawString(x, y, line)
        y -= line_height
        line_count += 1

    c.save()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 3:
        print("Usage: python build_closure_report.py <input.json> <output.pdf>",
              file=sys.stderr)
        sys.exit(1)
    in_json = Path(sys.argv[1])
    out_pdf = Path(sys.argv[2])
    if not in_json.exists():
        print(f"Input JSON not found: {in_json}", file=sys.stderr)
        sys.exit(2)

    data = json.loads(in_json.read_text())
    parcels = data.get("parcels", data) if isinstance(data, dict) else data

    all_lines = []
    for i, parcel in enumerate(parcels):
        all_lines.append(SEP)
        all_lines.extend(render_parcel_text(parcel))
    # Trailing separator to bookend the final parcel
    all_lines.append(SEP)

    render_pdf(all_lines, out_pdf)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
