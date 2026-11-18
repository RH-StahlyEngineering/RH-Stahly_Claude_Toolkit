# live-cad-edit / scripts / closure_report.ps1
#
# Build a multi-parcel closure-report PDF. See
# references/closure_report_conventions.md for the structure and conventions.
#
# Workflow:
#   1. This PowerShell wrapper pulls vertex coordinates from the open AutoCAD
#      drawing for the named parcels and writes them to a JSON file.
#   2. It then invokes the Python builder (build_closure_report.py) to
#      compute closure and assemble the PDF (reportlab + matplotlib).
#
# Usage:
#   pwsh -File closure_report.ps1 -Parcels @(
#       @{ Handle='1583E'; Name='Tract 2';     POBStrategy='NE-South' }
#       @{ Handle='15053'; Name='Tract 1';     POBStrategy='Vertex'; POBX=2366425.7942; POBY=1004963.0769; FirstLeg='SE' }
#       @{ Handle='156C0'; Name='COS 1999-02'; POBStrategy='NW-South' }
#   ) -OutPdf 'C:\Users\rharbach\AppData\Local\Temp\closure_report.pdf'
#
# Each parcel entry is a hashtable with at minimum:
#   Handle      hex handle of the AcDbPolyline
#   Name        human-readable header (e.g. "Tract 2")
#
# Optional POB controls (the Python builder rotates the vertex list to put the
# chosen POB at index 0 and reverses direction if needed):
#   POBStrategy   'NE-South' | 'NW-South' | 'SE-North' | 'SW-North'
#                 | 'NE-West' | ... | 'Vertex' | 'AsIs'
#   POBX, POBY    when POBStrategy = 'Vertex': locate nearest vertex to (POBX, POBY)
#   FirstLeg      desired first-leg direction (used with POBStrategy=Vertex):
#                 'N' 'S' 'E' 'W' 'NE' 'NW' 'SE' 'SW'
#                 If omitted, the natural traversal direction is kept.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][hashtable[]]$Parcels,
    [string]$OutPdf,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"

$doc = Connect-AutoCAD -Document $Document

# Ensure target output path
if (-not $OutPdf) {
    $OutPdf = Join-Path $env:TEMP "closure_report.pdf"
}
$workDir = Split-Path -Parent $OutPdf
if ($workDir -and -not (Test-Path $workDir)) {
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
}
$jsonPath = Join-Path (Split-Path -Parent $OutPdf) "closure_report_input.json"

# Pull vertices for each parcel
$payload = @()
foreach ($p in $Parcels) {
    if (-not $p.Handle) { throw "Each parcel entry needs a Handle." }
    $pl = $doc.HandleToObject([string]$p.Handle)
    if ($pl.ObjectName -ne 'AcDbPolyline') {
        throw "Handle '$($p.Handle)' is a $($pl.ObjectName), not AcDbPolyline."
    }
    $coords = $pl.Coordinates
    $n = $coords.Length / 2
    $verts = New-Object 'double[]' ($n * 2)
    for ($i = 0; $i -lt ($n * 2); $i++) { $verts[$i] = [double]$coords[$i] }

    $entry = @{
        Handle      = [string]$p.Handle
        Name        = if ($p.Name) { [string]$p.Name } else { [string]$p.Handle }
        Layer       = $pl.Layer
        Area        = [double]$pl.Area
        Verts       = $verts
        POBStrategy = if ($p.POBStrategy) { [string]$p.POBStrategy } else { 'AsIs' }
        POBX        = if ($p.POBX -ne $null) { [double]$p.POBX } else { $null }
        POBY        = if ($p.POBY -ne $null) { [double]$p.POBY } else { $null }
        FirstLeg    = if ($p.FirstLeg) { [string]$p.FirstLeg } else { $null }
    }
    $payload += $entry
    "Pulled $($p.Handle) ($($entry.Name)): $n verts, area=$([math]::Round($entry.Area / 43560, 4)) ac"
}

$payload | ConvertTo-Json -Depth 5 -Compress | Out-File $jsonPath -Encoding utf8
"Wrote $jsonPath"
""

# Invoke the Python builder
$pyScript = Join-Path $PSScriptRoot 'build_closure_report.py'
"Invoking Python builder: $pyScript"
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "Python not found on PATH." }

& $python $pyScript $jsonPath $OutPdf
if ($LASTEXITCODE -ne 0) { throw "build_closure_report.py exited with code $LASTEXITCODE" }

""
"Closure report written: $OutPdf"
