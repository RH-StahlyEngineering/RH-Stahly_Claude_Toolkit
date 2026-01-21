#!/usr/bin/env python3
"""Write decisions CSV from JSON, handling special characters correctly.

This script solves the problem where apostrophes in elevation values
(like "RIM ELEV = 3509.05'") break shell heredocs and the Write tool.
Python's csv module handles quoting correctly.

Usage:
    python write_decisions_csv.py <decisions.json> <output.csv>

Example:
    python ~/.claude/skills/dxf/scripts/write_decisions_csv.py decisions.json decisions.csv
"""
import csv
import json
import sys
from pathlib import Path


def write_decisions_csv(json_path: str, csv_path: str) -> int:
    """Write decisions JSON to CSV format.

    Args:
        json_path: Path to decisions JSON file
        csv_path: Path to write output CSV

    Returns:
        Number of rows written
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    labels = data.get('labels', [])
    count = 0

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)

        # Write header
        writer.writerow([
            'Point#', 'File', 'Code', 'Comment', 'Decision', 'Label_Text', 'Reasoning', 'Notes'
        ])

        # Write each label
        for label in labels:
            writer.writerow([
                label.get('point_num', ''),
                label.get('source_file', ''),
                label.get('code', ''),
                label.get('comment', ''),
                label.get('type', ''),
                label.get('label_text', ''),
                label.get('reasoning', ''),
                ''  # Notes column - empty for user corrections
            ])
            count += 1

    return count


def main():
    if len(sys.argv) < 3:
        print("Usage: python write_decisions_csv.py <decisions.json> <output.csv>", file=sys.stderr)
        print("\nWrites decisions JSON to CSV format, correctly handling special characters", file=sys.stderr)
        print("like apostrophes in elevation values (e.g., \"RIM ELEV = 3509.05'\").", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    csv_path = sys.argv[2]

    # Validate input exists
    if not Path(json_path).exists():
        print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    # Write CSV
    try:
        count = write_decisions_csv(json_path, csv_path)
        print(f"Wrote {count} rows to {csv_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_path}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error writing CSV: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
