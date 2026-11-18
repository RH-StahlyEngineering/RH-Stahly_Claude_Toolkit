# live-cad-edit / scripts / balance_area.ps1
#
# Perpendicular-shift solver: hold all bearings, move one segment of an
# LWPolyline perpendicular to itself to hit a target area exactly.
# Reports the suggested change but does NOT apply.
#
# Usage:
#   pwsh -File balance_area.ps1 -Handle 15053 -VaIdx 13 -VbIdx 14 -TargetAcres 20.0100
#
#   Va and Vb are 1-BASED polyline vertex numbers (as labeled in mapcheck output).
#   The segment Va->Vb is the one that gets shifted. Va's predecessor and Vb's
#   successor are the "fixed" adjacent vertices; their bearings are preserved.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Handle,
    [Parameter(Mandatory=$true)][int]$VaIdx,
    [Parameter(Mandatory=$true)][int]$VbIdx,
    [Parameter(Mandatory=$true)][double]$TargetAcres,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\bearing_math.ps1"
. "$PSScriptRoot\..\lib\geometry.ps1"
. "$PSScriptRoot\..\lib\solvers.ps1"

$doc = Connect-AutoCAD -Document $Document
$pl  = Get-PolylineByHandle -Doc $doc -Handle $Handle
Assert-NoBulges -Polyline $pl -Context 'balance_area'
$v   = Get-PolylineVerticesXY -Polyline $pl

# Convert 1-based to 0-based
$Va = $VaIdx - 1
$Vb = $VbIdx - 1

$targetSqFt = $TargetAcres * 43560.0
$currentArea = Shoelace-Area $v.X $v.Y
"Current area: {0:N4} sq ft ({1:F6} ac)" -f $currentArea, ($currentArea / 43560.0)
"Target area : {0:N4} sq ft ({1:F6} ac)" -f $targetSqFt, $TargetAcres
"Delta need  : {0:+0.0000;-0.0000;0.0000} sq ft" -f ($targetSqFt - $currentArea)
""

$result = Solve-PerpShift-ForArea -X $v.X -Y $v.Y -VaIdx $Va -VbIdx $Vb -TargetArea $targetSqFt

# Report
$shiftDir = if ($result.D -ge 0) { 'east / right of segment' } else { 'west / left of segment' }
""
"================ SUGGESTED CHANGE (NOT APPLIED) ================"
"Segment shift (perpendicular to L$VaIdx-L$VbIdx):"
"  d = {0:F4} ft   ({1})" -f $result.D, $shiftDir
""
"  P$VaIdx (old): ({0:F4}, {1:F4})" -f $v.X[$Va], $v.Y[$Va]
"  P$VaIdx (new): ({0:F4}, {1:F4})" -f $result.NewVaX, $result.NewVaY
"     slides {0:F4} ft along its incoming bearing" -f `
    ([Math]::Sqrt(($result.NewVaX-$v.X[$Va])*($result.NewVaX-$v.X[$Va]) + ($result.NewVaY-$v.Y[$Va])*($result.NewVaY-$v.Y[$Va])))
""
"  P$VbIdx (old): ({0:F4}, {1:F4})" -f $v.X[$Vb], $v.Y[$Vb]
"  P$VbIdx (new): ({0:F4}, {1:F4})" -f $result.NewVbX, $result.NewVbY
"     slides {0:F4} ft along its outgoing bearing" -f `
    ([Math]::Sqrt(($result.NewVbX-$v.X[$Vb])*($result.NewVbX-$v.X[$Vb]) + ($result.NewVbY-$v.Y[$Vb])*($result.NewVbY-$v.Y[$Vb])))
""

# Compute new course distances around the shifted segment
$n = $v.N
$iPrev = (($Va - 1 + $n) % $n)
$iNext = (($Vb + 1) % $n)
$Loldab = [Math]::Sqrt(($v.X[$Vb]-$v.X[$Va])*($v.X[$Vb]-$v.X[$Va]) + ($v.Y[$Vb]-$v.Y[$Va])*($v.Y[$Vb]-$v.Y[$Va]))
$Lold12 = [Math]::Sqrt(($v.X[$Va]-$v.X[$iPrev])*($v.X[$Va]-$v.X[$iPrev]) + ($v.Y[$Va]-$v.Y[$iPrev])*($v.Y[$Va]-$v.Y[$iPrev]))
$Lold14 = [Math]::Sqrt(($v.X[$iNext]-$v.X[$Vb])*($v.X[$iNext]-$v.X[$Vb]) + ($v.Y[$iNext]-$v.Y[$Vb])*($v.Y[$iNext]-$v.Y[$Vb]))
$Lnew12 = [Math]::Sqrt(($result.NewVaX-$v.X[$iPrev])*($result.NewVaX-$v.X[$iPrev]) + ($result.NewVaY-$v.Y[$iPrev])*($result.NewVaY-$v.Y[$iPrev]))
$Lnewab = [Math]::Sqrt(($result.NewVbX-$result.NewVaX)*($result.NewVbX-$result.NewVaX) + ($result.NewVbY-$result.NewVaY)*($result.NewVbY-$result.NewVaY))
$Lnew14 = [Math]::Sqrt(($v.X[$iNext]-$result.NewVbX)*($v.X[$iNext]-$result.NewVbX) + ($v.Y[$iNext]-$result.NewVbY)*($v.Y[$iNext]-$result.NewVbY))

"Course distances (only the 3 affected change):"
"  L{0,-2}  old: {1,9:F2} ft   new: {2,9:F2} ft   delta {3:+0.00;-0.00;0.00} ft" -f ($iPrev + 1), $Lold12, $Lnew12, ($Lnew12 - $Lold12)
"  L{0,-2}  old: {1,9:F2} ft   new: {2,9:F2} ft   delta {3:+0.00;-0.00;0.00} ft" -f $VaIdx, $Loldab, $Lnewab, ($Lnewab - $Loldab)
"  L{0,-2}  old: {1,9:F2} ft   new: {2,9:F2} ft   delta {3:+0.00;-0.00;0.00} ft" -f $VbIdx, $Lold14, $Lnew14, ($Lnew14 - $Lold14)
""
"Final area: {0:N4} sq ft = {1:F6} ac" -f $result.FinalArea, ($result.FinalArea / 43560.0)
"Residual  : {0:E3} sq ft" -f $result.Residual
""
"To apply, run scripts\apply_vertex_moves.ps1 with:"
"  -Handle $Handle  -VertexIndex $VaIdx  -NewX {0:F4}  -NewY {1:F4}" -f $result.NewVaX, $result.NewVaY
"  -Handle $Handle  -VertexIndex $VbIdx  -NewX {0:F4}  -NewY {1:F4}" -f $result.NewVbX, $result.NewVbY
""
"Reminder: if either of P$VaIdx / P$VbIdx is coincident with a vertex on"
"an adjoining polyline, update that polyline's matching vertex too."
