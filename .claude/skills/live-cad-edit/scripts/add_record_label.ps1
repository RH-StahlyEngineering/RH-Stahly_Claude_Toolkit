# live-cad-edit / scripts / add_record_label.ps1
#
# Add a Stahly-style record-measurement label alongside a line. See
# references/record_label_conventions.md for the convention notes.
#
# Usage:
#   pwsh -File add_record_label.ps1 -LineHandle 184EB `
#       -Measurement "GLO = 2673.00'" -ReferenceNumber 1
#
# Options:
#   -PaperOffset   0.27        # perpendicular offset in paper inches
#   -OffsetSide    'right'     # 'right' or 'left' of line start->end direction
#   -AlongFraction 0.5         # 0..1 position along the line (default = midpoint)
#   -AnnoScale     "1\" = 1000'"  # target CANNOSCALE; default = current
#   -StyleName     'Annotative Italic-0.08'
#   -LayerName     'V-BNDY-REC-TEXT'
#   -PaperHeight   0.08
#   -Document      <name or index when multiple docs open>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$LineHandle,
    [Parameter(Mandatory=$true)][string]$Measurement,
    [int]$ReferenceNumber   = 0,    # 0 = distance-only label, no (R<N>) subscript
    [double]$PaperOffset    = 0.27,
    [ValidateSet('right','left')][string]$OffsetSide = 'right',
    [double]$AlongFraction  = 0.5,
    [string]$AnnoScale,
    [double]$AnnoScaleFactor = 0,   # numeric override (e.g. 100 for 1"=100')
    [string]$StyleName      = 'Annotative Italic-0.08',
    [string]$LayerName      = 'V-BNDY-REC-TEXT',
    [double]$PaperHeight    = 0.08,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\mtext_helpers.ps1"

$doc = Connect-AutoCAD -Document $Document
$line = Get-LineByHandle -Doc $doc -Handle $LineHandle

# Geometry of the line
$sp = $line.StartPoint
$ep = $line.EndPoint
$dx = $ep[0] - $sp[0]
$dy = $ep[1] - $sp[1]
$L  = [Math]::Sqrt($dx*$dx + $dy*$dy)
$ux = $dx / $L; $uy = $dy / $L
# Perpendicular: right-of-direction (start->end) is (uy, -ux); left is (-uy, ux)
if ($OffsetSide -eq 'right') { $nx =  $uy; $ny = -$ux }
else                          { $nx = -$uy; $ny =  $ux }

# Determine annotation scale factor for offset computation.
# Explicit AnnoScaleFactor wins; else parse from AnnoScale; else from current CANNOSCALE.
if ($AnnoScaleFactor -gt 0) {
    $scaleFactor = $AnnoScaleFactor
    $activeScale = $AnnoScale  # may be blank; only used for reporting
} else {
    $activeScale = $AnnoScale
    if (-not $activeScale) {
        try { $activeScale = $doc.GetVariable('CANNOSCALE') } catch {}
    }
    $scaleFactor = Get-AnnoScaleFactor -ScaleName $activeScale
}
$modelOffset = $PaperOffset * $scaleFactor

# Insertion point: along + perpendicular offset
$ax = $sp[0] + $L * $AlongFraction * $ux
$ay = $sp[1] + $L * $AlongFraction * $uy
$insertX = $ax + $modelOffset * $nx
$insertY = $ay + $modelOffset * $ny

# Rotation: align text with the line's bearing using the surveyor convention.
# For NW/SE-pointing lines (S..E and N..W bearings): rotation = pi/2 + bearing_rad   (near-vertical text)
# For NE/SW-pointing lines (N..E and S..W bearings): rotation = pi/2 - bearing_rad   (near-horizontal text)
# This matches record_label_conventions.md and produces 93.9° for S 03°53'52" E, etc.
$brgFromN = [Math]::Atan2([Math]::Abs($ux), [Math]::Abs($uy))
$isNW_SE = (($uy -ge 0 -and $ux -lt 0) -or ($uy -lt 0 -and $ux -ge 0))
if ($isNW_SE) { $rotRad = [Math]::PI / 2.0 + $brgFromN }
else          { $rotRad = [Math]::PI / 2.0 - $brgFromN }

# Content. Distance-only labels (ReferenceNumber=0) skip the (R<N>) subscript.
if ($ReferenceNumber -gt 0) {
    $content = "\A1;$Measurement (R{\H0.7x;\S^$ReferenceNumber;})"
} else {
    $content = "\A1;$Measurement"
}

$mt = Add-AnnotativeMText `
    -Doc $doc `
    -InsertX $insertX -InsertY $insertY `
    -Content $content `
    -StyleName $StyleName `
    -LayerName $LayerName `
    -RotationRad $rotRad `
    -PaperHeight $PaperHeight `
    -AnnoScaleName $activeScale `
    -AnnoScaleFactor $AnnoScaleFactor

"---- Record label created ----"
"  Handle:        $($mt.Handle)"
"  Layer:         $($mt.Layer)"
"  Style:         $($mt.StyleName)"
"  Height:        $($mt.Height) (model)   paper={0:F4} in" -f $PaperHeight
"  Rotation:      {0:F6} rad = {1:F4}°" -f $rotRad, ($rotRad * 180 / [Math]::PI)
"  Insertion:     ({0:F4}, {1:F4})" -f $insertX, $insertY
"  Offset:        $PaperOffset paper-in × $scaleFactor = $modelOffset model-ft  ($OffsetSide of line)"
"  Along line:    fraction=$AlongFraction  ({0:F2} ft from start)" -f ($L * $AlongFraction)
if ($activeScale) {
    "  Anno scale:    $activeScale (factor $scaleFactor)"
} else {
    "  Anno scale:    factor $scaleFactor (no CANNOSCALE name; use SCALELISTEDIT+OBJECTSCALE to attach)"
}
"  Content:       $content"
""
"Drawing not saved. Review in AutoCAD, adjust position if needed, then save."
