# live-cad-edit / scripts / mapcheck.ps1
#
# Closure / inverse listing / area / precision-ratio report for an
# LWPolyline identified by hex handle. No edits.
#
# Usage:
#   pwsh -File mapcheck.ps1 -Handle 15053

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Handle,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\bearing_math.ps1"
. "$PSScriptRoot\..\lib\geometry.ps1"

$doc = Connect-AutoCAD -Document $Document
$pl  = Get-PolylineByHandle -Doc $doc -Handle $Handle
Assert-NoBulges -Polyline $pl -Context 'mapcheck'
$v = Get-PolylineVerticesXY -Polyline $pl

$area    = Shoelace-Area $v.X $v.Y
$acres   = $area / 43560.0
$layer   = $pl.Layer

# Build segments (with rounded bearings/distances for re-inverse)
$courses = New-Object 'System.Collections.Generic.List[object]'
$perim   = 0.0
for ($i = 0; $i -lt $v.N; $i++) {
    $j = ($i + 1) % $v.N
    $dx = $v.X[$j] - $v.X[$i]
    $dy = $v.Y[$j] - $v.Y[$i]
    $L  = [Math]::Sqrt($dx*$dx + $dy*$dy)
    $perim += $L

    $brgStr = Format-Bearing -dx $dx -dy $dy
    $brgParsed = Parse-Bearing $brgStr     # rounded bearing as unit vector
    $LRound = [Math]::Round($L, 2)

    $courses.Add([pscustomobject]@{
        Idx = $i + 1
        BrgStr = $brgStr
        BrgUx = $brgParsed.ux
        BrgUy = $brgParsed.uy
        LenRaw = $L
        LenRound = $LRound
        FromX = $v.X[$i]; FromY = $v.Y[$i]
        ToX = $v.X[$j];   ToY = $v.Y[$j]
    })
}

# Re-inverse from POB using rounded values; compute misclose
$cX = $v.X[0]; $cY = $v.Y[0]
foreach ($c in $courses) {
    $cX += $c.BrgUx * $c.LenRound
    $cY += $c.BrgUy * $c.LenRound
}
$mX = $cX - $v.X[0]   # closure error in X
$mY = $cY - $v.Y[0]   # closure error in Y
$errLen = [Math]::Sqrt($mX*$mX + $mY*$mY)
$precision = if ($errLen -lt 1e-9) { [double]::PositiveInfinity } else { $perim / $errLen }
$errBrg = if ($errLen -lt 1e-9) { '(exact closure)' } else { Format-Bearing -dx $mX -dy $mY }

"PARCEL MAPCHECK -- handle $Handle  layer $layer"
"Vertices: $($v.N)  (closed polyline)"
""
"Raw geometry:"
"  Area      : {0:N4} sq ft  ({1:F6} ac)" -f $area, $acres
"  Perimeter : {0:N4} ft" -f $perim
""
"Mapcheck (bearings rounded to nearest second, distances to 0.01 ft):"
"  Misclose dN : {0:F4} ft" -f $mY
"  Misclose dE : {0:F4} ft" -f $mX
"  Error dist  : {0:F4} ft   bearing {1}" -f $errLen, $errBrg
if ([double]::IsInfinity($precision)) {
    "  Precision   : exact (no rounding-induced misclosure)"
} else {
    "  Precision   : 1 : {0:N0}" -f $precision
}
""
"COURSES (POB = P1):"
"  P1  = ({0:F4}, {1:F4})" -f $v.X[0], $v.Y[0]
foreach ($c in $courses) {
    "  L{0,-2}  {1}  {2,9:F2} ft   ->  P{3}  ({4:F4}, {5:F4})" -f `
        $c.Idx, $c.BrgStr, $c.LenRound, ((($c.Idx) % $v.N) + 1), $c.ToX, $c.ToY
}
