#!/usr/bin/env python3
"""
Parse CSV files in PNEZD format (Point, Northing, Easting, Elevation, Description).
Outputs JSON for Claude to analyze and make labeling decisions.
"""

import sys
import json
import csv
import argparse
from pathlib import Path


def detect_delimiter(line):
    """Auto-detect CSV delimiter from first line."""
    for delim in [',', '\t', ';']:
        if delim in line:
            return delim
    return ','


def is_header_row(row):
    """Check if row is a header (first field is non-numeric)."""
    if not row:
        return False
    try:
        float(row[0])
        return False
    except ValueError:
        return True


def parse_csv_pnezd(file_path, filter_slash=True):
    """
    Parse a CSV file in PNEZD format.

    PNEZD columns: Point, Northing, Easting, Elevation, Description
    Coordinate mapping: x = Easting, y = Northing, z = Elevation
    """
    points = []
    errors = []

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        # Read first line to detect delimiter
        first_line = f.readline()
        delimiter = detect_delimiter(first_line)
        f.seek(0)

        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        return points, ["Empty CSV file"]

    # Skip header if present
    start_idx = 1 if is_header_row(rows[0]) else 0

    for i, row in enumerate(rows[start_idx:], start=start_idx + 1):
        if len(row) < 5:
            errors.append(f"Row {i}: Expected 5 columns (PNEZD), got {len(row)}")
            continue

        point_num, northing, easting, elevation, description = row[0], row[1], row[2], row[3], row[4]

        # Validate numeric fields
        try:
            n = float(northing)
            e = float(easting)
            z = float(elevation)
        except ValueError as ex:
            errors.append(f"Row {i}: Invalid numeric value - {ex}")
            continue

        description = description.strip()

        # Filter for "/" in description if requested
        if filter_slash and '/' not in description:
            continue

        # Parse code and comment
        if '/' in description:
            parts = description.split('/', 1)
            code = parts[0].strip().upper()
            comment = parts[1].strip() if len(parts) > 1 else ""
        else:
            code = description.upper()
            comment = ""

        points.append({
            'block_name': None,  # No DXF block for CSV input
            'point_num': point_num.strip(),
            'elevation': elevation.strip(),
            'description': description,
            'code': code,
            'comment': comment,
            'position': {
                'x': e,  # Easting = X
                'y': n,  # Northing = Y
                'z': z   # Elevation = Z
            }
        })

    return points, errors


def main():
    parser = argparse.ArgumentParser(
        description='Parse CSV files in PNEZD format (Point, Northing, Easting, Elevation, Description).'
    )
    parser.add_argument('input_csv', nargs='+', help='Input CSV file path(s)')
    parser.add_argument('--no-filter', action='store_true',
                        help='Include all points, not just those with "/" in description')

    args = parser.parse_args()

    all_points = []
    all_errors = []
    source_files = []

    for csv_path in args.input_csv:
        input_path = Path(csv_path)

        if not input_path.exists():
            print(json.dumps({'error': f'Input file not found: {csv_path}'}))
            sys.exit(1)

        if input_path.is_dir():
            # Process all CSV files in directory
            csv_files = list(input_path.glob('*.csv'))
            if not csv_files:
                print(json.dumps({'error': f'No CSV files found in directory: {csv_path}'}))
                sys.exit(1)
            for csv_file in csv_files:
                points, errors = parse_csv_pnezd(csv_file, filter_slash=not args.no_filter)
                all_points.extend(points)
                all_errors.extend([f"{csv_file.name}: {e}" for e in errors])
                source_files.append(str(csv_file.absolute()))
        else:
            points, errors = parse_csv_pnezd(input_path, filter_slash=not args.no_filter)
            all_points.extend(points)
            all_errors.extend(errors)
            source_files.append(str(input_path.absolute()))

    # Output JSON
    result = {
        'source_file': source_files[0] if len(source_files) == 1 else source_files,
        'mleader_style': 'Annotative-Simplex',
        'point_count': len(all_points),
        'points': all_points
    }

    if all_errors:
        result['warnings'] = all_errors

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
