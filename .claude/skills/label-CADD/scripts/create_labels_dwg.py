#!/usr/bin/env python3
"""
Create MULTILEADER labels using AutoCAD's native MLEADER command via AcCoreConsole.

This wrapper script:
1. Converts decisions.json to CSV format for AutoLISP
2. Creates an AcCoreConsole script file
3. Runs AcCoreConsole with the template DWG and AutoLISP script
4. Returns the output DWG path

Why this approach?
ezdxf cannot produce annotative MULTILEADER entities that fully work in AutoCAD
(copy/paste issues, XREF issues, scaling issues). By using AutoCAD's native MLEADER
command through AcCoreConsole, we get guaranteed compatibility.
"""

import sys
import json
import argparse
import subprocess
import tempfile
import time
from pathlib import Path

# AcCoreConsole paths to search (in order of preference)
ACCORECONSOLE_PATHS = [
    r"C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2023\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD LT 2025\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD LT 2024\accoreconsole.exe",
]

# Default template DWG (will be created from DXF on first use)
DEFAULT_TEMPLATE = Path(__file__).parent.parent / "templates" / "mleader-template.dwg"
FALLBACK_TEMPLATE_DXF = Path(__file__).parent.parent / "templates" / "mleader-template.dxf"

# AutoLISP script location
LISP_SCRIPT = Path(__file__).parent / "create_mleaders.lsp"

# Color constants
COLOR_BYLAYER = 256
COLOR_RED = 1


def find_accoreconsole():
    """Find AcCoreConsole executable."""
    for path in ACCORECONSOLE_PATHS:
        if Path(path).exists():
            return path
    return None


def convert_decisions_to_csv(decisions_json, output_csv):
    """Convert decisions.json to CSV format for AutoLISP.

    CSV format: Point#,X,Y,Z,Label_Text,Type,Layer,Color

    Args:
        decisions_json: Path to decisions.json file
        output_csv: Path to write CSV output

    Returns:
        Number of labels converted
    """
    with open(decisions_json, 'r') as f:
        decisions = json.load(f)

    labels = decisions.get('labels', [])
    count = 0

    with open(output_csv, 'w', encoding='utf-8') as f:
        # Write header
        f.write("# Labels CSV for AutoLISP MLEADER creation\n")
        f.write("Point#,X,Y,Z,Label_Text,Type,Layer,Color\n")

        for label in labels:
            position = label.get('position')
            if not position:
                continue

            label_text = label.get('label_text', '')
            if not label_text:
                continue

            label_type = label.get('type', 'presentation')
            if label_type == 'skip':
                continue

            point_num = label.get('point_num', '')
            x = position.get('x', 0)
            y = position.get('y', 0)
            z = position.get('z', 0)

            # Determine layer and color based on type
            if label_type == 'drafter':
                layer = '0'
                color = COLOR_RED
            else:
                layer = 'G-ANNO'
                color = COLOR_BYLAYER
                label_text = label_text.upper()  # ALL CAPS for presentation

            # Escape commas in label text (wrap in quotes if needed)
            if ',' in label_text:
                label_text = f'"{label_text}"'

            f.write(f"{point_num},{x},{y},{z},{label_text},{label_type},{layer},{color}\n")
            count += 1

    return count


def create_script_file(lisp_path, csv_path, output_dwg, script_path, scale):
    """Create AcCoreConsole script file.

    Args:
        lisp_path: Path to create_mleaders.lsp
        csv_path: Path to labels CSV
        output_dwg: Path for output DWG
        script_path: Path to write script file
        scale: Annotative scale factor (e.g., 40 for 1:40)
    """
    # Convert paths to absolute and forward slashes for AutoLISP
    lisp_path_str = str(lisp_path.resolve()).replace('\\', '/')
    csv_path_str = str(csv_path.resolve()).replace('\\', '/')
    output_dwg_str = str(output_dwg.resolve()).replace('\\', '/')

    # Script uses SECURELOAD 0 to allow loading LISP from any path
    # Then loads and runs the LISP script
    script_content = f''';;; AcCoreConsole script for MLEADER batch creation
;;; Disable SECURELOAD to allow LISP loading from any path
(setvar "SECURELOAD" 0)

;;; Load the LISP script
(load "{lisp_path_str}")

;;; Create the labels with specified scale
(c:MLEADER-BATCH "{csv_path_str}" "{output_dwg_str}" {scale})

;;; Exit
(command "._QUIT" "_Yes")
'''

    with open(script_path, 'w') as f:
        f.write(script_content)


def run_accoreconsole(accore_path, template_dwg, script_path, timeout=300):
    """Run AcCoreConsole with template and script.

    Args:
        accore_path: Path to accoreconsole.exe
        template_dwg: Path to template DWG file
        script_path: Path to script file (.scr or .lsp)
        timeout: Maximum seconds to wait

    Returns:
        (success, stdout, stderr)
    """
    # AcCoreConsole arguments:
    # /i <drawing> - Input drawing to open
    # /s <script> - Script file to run
    # /l <language> - Language code
    cmd = [
        accore_path,
        "/i", str(template_dwg),
        "/s", str(script_path),
    ]

    print(f"Running: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(template_dwg.parent)  # Set working directory
        )
        return (result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "AcCoreConsole timed out")
    except Exception as e:
        return (False, "", str(e))


def create_manual_script(lisp_path, csv_path, output_dwg, script_path):
    """Create a manual SCR script for users who can't run AcCoreConsole.

    This creates a .scr file that users can drag-drop into AutoCAD.

    Args:
        lisp_path: Path to create_mleaders.lsp
        csv_path: Path to labels CSV
        output_dwg: Path for output DWG
        script_path: Path to write script file
    """
    lisp_path_str = str(lisp_path).replace('\\', '/')
    csv_path_str = str(csv_path).replace('\\', '/')
    output_dwg_str = str(output_dwg).replace('\\', '/')

    # SCR files use command-line syntax
    script_content = f''';;; Manual script for MLEADER creation
;;; Drag this file into AutoCAD with the template DWG open
;;;
;;; Steps:
;;; 1. Open the template DWG in AutoCAD
;;; 2. Drag this .scr file into the drawing window
;;; 3. Wait for completion
;;; 4. Check the output file location

(load "{lisp_path_str}")
(c:CREATE-MLEADERS "{csv_path_str}")
_SAVEAS
2018
{output_dwg_str}

'''

    with open(script_path, 'w') as f:
        f.write(script_content)


def main():
    parser = argparse.ArgumentParser(
        description='Create MULTILEADER labels using AutoCAD native commands via AcCoreConsole.'
    )
    parser.add_argument('decisions_json', help='JSON file with labeling decisions')
    parser.add_argument('--scale', type=float, default=40,
                       help='Annotative scale factor (default: 40 for 1"=40\')')
    parser.add_argument('--output', '-o', help='Output DWG file path')
    parser.add_argument('--template', '-t', help='Template DWG file (default: bundled)')
    parser.add_argument('--accoreconsole', help='Path to accoreconsole.exe')
    parser.add_argument('--manual-only', action='store_true',
                       help='Only generate manual script, don\'t run AcCoreConsole')
    parser.add_argument('--timeout', type=int, default=300,
                       help='AcCoreConsole timeout in seconds (default: 300)')

    args = parser.parse_args()

    # Validate inputs
    decisions_path = Path(args.decisions_json)
    if not decisions_path.exists():
        print(json.dumps({
            'success': False,
            'error': f'Decisions file not found: {args.decisions_json}'
        }))
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        base = decisions_path.stem
        if base.endswith('-decisions'):
            base = base[:-10]
        output_path = decisions_path.parent / f"{base}-LABELS.dwg"

    # Find AcCoreConsole
    accore_path = args.accoreconsole
    if not accore_path:
        accore_path = find_accoreconsole()

    if not accore_path and not args.manual_only:
        print("Warning: AcCoreConsole not found. Generating manual script only.", file=sys.stderr)
        args.manual_only = True

    # Find or create template
    template_path = Path(args.template) if args.template else DEFAULT_TEMPLATE
    if not template_path.exists():
        if FALLBACK_TEMPLATE_DXF.exists():
            print(f"Warning: Template DWG not found at {template_path}", file=sys.stderr)
            print(f"  Using DXF template: {FALLBACK_TEMPLATE_DXF}", file=sys.stderr)
            print(f"  Note: Convert to DWG for best results.", file=sys.stderr)
            template_path = FALLBACK_TEMPLATE_DXF
        else:
            print(json.dumps({
                'success': False,
                'error': f'Template not found: {template_path}'
            }))
            sys.exit(1)

    # Validate LISP script exists
    if not LISP_SCRIPT.exists():
        print(json.dumps({
            'success': False,
            'error': f'LISP script not found: {LISP_SCRIPT}'
        }))
        sys.exit(1)

    # Create temp directory for intermediate files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Convert decisions.json to CSV
        csv_path = tmpdir / "labels.csv"
        print(f"Converting decisions to CSV...", file=sys.stderr)
        label_count = convert_decisions_to_csv(decisions_path, csv_path)
        print(f"  {label_count} labels to create", file=sys.stderr)

        if label_count == 0:
            print(json.dumps({
                'success': False,
                'error': 'No labels found in decisions file'
            }))
            sys.exit(1)

        # Create script file
        script_path = tmpdir / "create_labels.scr"

        if args.manual_only:
            # Generate manual script in output directory
            manual_script_path = output_path.with_suffix('.scr')
            manual_csv_path = output_path.with_name(output_path.stem + '-labels.csv')

            # Copy CSV to permanent location
            import shutil
            shutil.copy(csv_path, manual_csv_path)

            # Create manual script
            create_manual_script(LISP_SCRIPT, manual_csv_path, output_path, manual_script_path)

            print(f"\nManual mode: Scripts generated.", file=sys.stderr)
            print(f"  CSV file: {manual_csv_path}", file=sys.stderr)
            print(f"  Script file: {manual_script_path}", file=sys.stderr)
            print(f"\nTo create labels manually:", file=sys.stderr)
            print(f"  1. Open {template_path} in AutoCAD", file=sys.stderr)
            print(f"  2. Type: (load \"{LISP_SCRIPT}\")", file=sys.stderr)
            print(f"  3. Type: (c:CREATE-MLEADERS \"{manual_csv_path}\")", file=sys.stderr)
            print(f"  4. Save as: {output_path}", file=sys.stderr)

            print(json.dumps({
                'success': True,
                'manual_mode': True,
                'csv_file': str(manual_csv_path.absolute()),
                'script_file': str(manual_script_path.absolute()),
                'template_file': str(template_path.absolute()),
                'labels_count': label_count,
                'instructions': [
                    f"Open {template_path} in AutoCAD",
                    f"Load LISP: (load \"{LISP_SCRIPT}\")",
                    f"Run: (c:CREATE-MLEADERS \"{manual_csv_path}\")",
                    f"Save as: {output_path}"
                ]
            }))
            sys.exit(0)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create AcCoreConsole script
        create_script_file(LISP_SCRIPT, csv_path, output_path, script_path, args.scale)

        # Run AcCoreConsole with progress feedback
        estimated_time = 30 + label_count * 2  # Civil 3D load + ~2s per label
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Creating {label_count} MULTILEADER labels via AcCoreConsole...", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"  Template: {template_path}", file=sys.stderr)
        print(f"  Output: {output_path}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"  NOTE: Civil 3D/AutoCAD takes 30-60 seconds to load", file=sys.stderr)
        print(f"        before processing begins. This is normal.", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"  Estimated time: {estimated_time} seconds ({estimated_time // 60}m {estimated_time % 60}s)", file=sys.stderr)
        print(f"  Please wait - DO NOT interrupt the process!", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        success, stdout, stderr = run_accoreconsole(
            accore_path, template_path, script_path, args.timeout
        )

        if stdout:
            print(f"\n--- AcCoreConsole Output ---\n{stdout}", file=sys.stderr)
        if stderr:
            print(f"\n--- AcCoreConsole Errors ---\n{stderr}", file=sys.stderr)

        # Check for log file
        log_file = csv_path.parent / "create_mleaders.log"
        log_content = None
        if log_file.exists():
            log_content = log_file.read_text()
            print(f"\n--- LISP Log ---\n{log_content}", file=sys.stderr)

        # Verify output exists
        if output_path.exists():
            print(f"\nSuccess! Output saved to: {output_path}", file=sys.stderr)
            print(json.dumps({
                'success': True,
                'output_file': str(output_path.absolute()),
                'labels_count': label_count,
                'accoreconsole_used': True
            }))
        else:
            # AcCoreConsole may have failed - provide manual fallback
            print(f"\nWarning: Output file not created. Generating manual script...", file=sys.stderr)

            manual_script_path = output_path.with_suffix('.scr')
            manual_csv_path = output_path.with_name(output_path.stem + '-labels.csv')

            import shutil
            shutil.copy(csv_path, manual_csv_path)
            create_manual_script(LISP_SCRIPT, manual_csv_path, output_path, manual_script_path)

            print(json.dumps({
                'success': False,
                'error': 'AcCoreConsole did not create output file',
                'fallback': 'manual_script',
                'csv_file': str(manual_csv_path.absolute()),
                'script_file': str(manual_script_path.absolute()),
                'instructions': [
                    f"Open {template_path} in AutoCAD",
                    f"Load LISP: (load \"{LISP_SCRIPT}\")",
                    f"Run: (c:CREATE-MLEADERS \"{manual_csv_path}\")",
                    f"Save as: {output_path}"
                ]
            }))
            sys.exit(1)


if __name__ == '__main__':
    main()
