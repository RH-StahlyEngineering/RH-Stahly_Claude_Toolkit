# live-cad-edit / scripts / rotate_segments.ps1
#
# Rotate one or two segments of a closed LWPolyline to a target bearing,
# placing the moved vertex at the intersection of the target bearing line
# with a parallel offset of a reference line (so the rotated segment ends up
# the right perpendicular distance from a section / ROW / other reference).
# Then re-solve perpendicular shift on a different segment to restore a
# target area.
#
# This is the script for the canonical "rotate L7 and L9 to match the
# midsection bearing while staying 60 ft south of the section north line,
# and keep 20.0100 ac" problem.
#
# Reports the suggested change but does NOT apply.
#
# Usage:
#   pwsh -File rotate_segments.ps1 \
#       -Handle 15053 `
#       -RotateVertex 8 -FixedNeighborVertex 7 -TargetBearing 'N 03°04'10.03" W' `
#                                          -RefHandle '14AF8' -OffsetFt 60 -RefSide 1 `
#       -RotateVertex 9 -FixedNeighborVertex 10 -TargetBearing 'N 03°04'10.03" W' `
#                                          -RefHandle '14AF9' -OffsetFt 60 -RefSide 1 `
#       -BalanceVaIdx 13 -BalanceVbIdx 14 -TargetAcres 20.0100
#
# Because PowerShell -F can't naturally take repeated tuples, this script
# accepts arrays of equal length (one entry per rotation):

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Handle,
    [Parameter(Mandatory=$true)][int[]]$RotateVertex,
    [Parameter(Mandatory=$true)][int[]]$FixedNeighborVertex,
    [Parameter(Mandatory=$true)][string[]]$TargetBearing,
    [Parameter(Mandatory=$true)][string[]]$RefHandle,
    [Parameter(Mandatory=$true)][double[]]$OffsetFt,
    [Parameter(Mandatory=$true)][int[]]$RefSide,
    [Parameter(Mandatory=$true)][int]$BalanceVaIdx,
    [Parameter(Mandatory=$true)][int]$BalanceVbIdx,
    [Parameter(Mandatory=$true)][double]$TargetAcres,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\bearing_math.ps1"
. "$PSScriptRoot\..\lib\geometry.ps1"
. "$PSScriptRoot\..\lib\solvers.ps1"

$N = $RotateVertex.Count
if ($FixedNeighborVertex.Count -ne $N -or $TargetBearing.Count -ne $N -or $RefHandle.Count -ne $N -or $OffsetFt.Count -ne $N -or $RefSide.Count -ne $N) {
    throw "All rotation parameter arrays must have the same length (one entry per rotation)."
}

$doc = Connect-AutoCAD -Document $Document
$pl  = Get-PolylineByHandle -Doc $doc -Handle $Handle
Assert-NoBulges -Polyline $pl -Context 'rotate_segments'
$v   = Get-PolylineVerticesXY -Polyline $pl

"Rotating $N segment(s) on polyline $Handle..."
""

# Compute each new vertex position
$X = $v.X.Clone(); $Y = $v.Y.Clone()
$newPositions = @()
for ($r = 0; $r -lt $N; $r++) {
    $idxRot = $RotateVertex[$r] - 1     # 0-based vertex to move
    $idxFix = $FixedNeighborVertex[$r] - 1
    $brg = Parse-Bearing -Text $TargetBearing[$r]
    # We want the line FROM the fixed neighbor TOWARDS where the rotated vertex
    # will end up; "going N" means brg.uy > 0. If the new vertex is north of the
    # fixed neighbor (typical for L7), use brg as-is. If south, flip.
    # Heuristic: pick the direction that points from fixed to current rotated
    # vertex (so a small rotation keeps us in the right half-line).
    $cdx = $X[$idxRot] - $X[$idxFix]
    $cdy = $Y[$idxRot] - $Y[$idxFix]
    if (($cdx * $brg.ux + $cdy * $brg.uy) -lt 0) {
        $brg.ux = -$brg.ux; $brg.uy = -$brg.uy
    }

    # Reference line endpoints from the referenced AcDbLine
    $refLine = Invoke-WithComRetry { $doc.HandleToObject($RefHandle[$r]) }
    if ($null -eq $refLine) { throw "Reference line handle '$($RefHandle[$r])' not found." }
    if ($refLine.ObjectName -ne 'AcDbLine') { throw "Reference handle '$($RefHandle[$r])' is a $($refLine.ObjectName), not AcDbLine." }
    $refA = $refLine.StartPoint; $refB = $refLine.EndPoint

    $newPt = Solve-BearingIntersection `
        -FixedX $X[$idxFix] -FixedY $Y[$idxFix] `
        -Ubrgx $brg.ux -Ubrgy $brg.uy `
        -RefAx $refA[0] -RefAy $refA[1] `
        -RefBx $refB[0] -RefBy $refB[1] `
        -Dist $OffsetFt[$r] -Side $RefSide[$r]

    "Rotation $($r+1):  v$($RotateVertex[$r]) to target bearing $($TargetBearing[$r]) from v$($FixedNeighborVertex[$r])"
    "    fixed: ({0:F4}, {1:F4})" -f $X[$idxFix], $Y[$idxFix]
    "    old  : ({0:F4}, {1:F4})" -f $X[$idxRot], $Y[$idxRot]
    "    new  : ({0:F4}, {1:F4})" -f $newPt.X, $newPt.Y
    $shift = [Math]::Sqrt(($newPt.X - $X[$idxRot])*($newPt.X - $X[$idxRot]) + ($newPt.Y - $Y[$idxRot])*($newPt.Y - $Y[$idxRot]))
    "    shift: {0:F4} ft" -f $shift
    ""

    $X[$idxRot] = $newPt.X; $Y[$idxRot] = $newPt.Y
    $newPositions += [pscustomobject]@{ Vertex = $RotateVertex[$r]; X = $newPt.X; Y = $newPt.Y; Shift = $shift }
}

# After all rotations, compute area
$areaAfterRot = Shoelace-Area $X $Y
"Area after rotation(s): {0:N4} sq ft  ({1:F6} ac)" -f $areaAfterRot, ($areaAfterRot / 43560.0)
$target = $TargetAcres * 43560.0
"Target area:             {0:N4} sq ft  ({1:F6} ac)" -f $target, $TargetAcres
"Delta to absorb in L${BalanceVaIdx}-L${BalanceVbIdx} shift: {0:+0.00;-0.00;0.00} sq ft" -f ($target - $areaAfterRot)
""

# Now solve perpendicular shift on L_Va-L_Vb to restore area
$balance = Solve-PerpShift-ForArea -X $X -Y $Y -VaIdx ($BalanceVaIdx - 1) -VbIdx ($BalanceVbIdx - 1) -TargetArea $target
"Perpendicular shift of segment L${BalanceVaIdx}-L${BalanceVbIdx}: {0:F4} ft" -f $balance.D
""

$newPositions += [pscustomobject]@{ Vertex = $BalanceVaIdx; X = $balance.NewVaX; Y = $balance.NewVaY; Shift = [Math]::Sqrt(($balance.NewVaX-$v.X[$BalanceVaIdx-1])*($balance.NewVaX-$v.X[$BalanceVaIdx-1]) + ($balance.NewVaY-$v.Y[$BalanceVaIdx-1])*($balance.NewVaY-$v.Y[$BalanceVaIdx-1])) }
$newPositions += [pscustomobject]@{ Vertex = $BalanceVbIdx; X = $balance.NewVbX; Y = $balance.NewVbY; Shift = [Math]::Sqrt(($balance.NewVbX-$v.X[$BalanceVbIdx-1])*($balance.NewVbX-$v.X[$BalanceVbIdx-1]) + ($balance.NewVbY-$v.Y[$BalanceVbIdx-1])*($balance.NewVbY-$v.Y[$BalanceVbIdx-1])) }

"================ SUGGESTED CHANGES (NOT APPLIED) ================"
"Apply these vertex updates to polyline $Handle (and to any adjoining polylines that share these vertices):"
foreach ($p in $newPositions) {
    "  v{0,-2}  -> ({1:F4}, {2:F4})   shift {3:F4} ft" -f $p.Vertex, $p.X, $p.Y, $p.Shift
}
""
"Final area: {0:N4} sq ft = {1:F6} ac" -f $balance.FinalArea, ($balance.FinalArea / 43560.0)
"Residual  : {0:E3} sq ft" -f $balance.Residual
