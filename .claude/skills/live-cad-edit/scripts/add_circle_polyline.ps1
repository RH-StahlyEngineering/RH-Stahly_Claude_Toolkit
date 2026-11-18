# live-cad-edit / scripts / add_circle_polyline.ps1
#
# Create a closed LWPolyline approximating a circle. Useful when you need a
# circle as a snap target, tolerance circle, or constraint surface — i.e. when
# the "circle" must behave like a polyline (vertices addressable by COM,
# closure checks via the topology audit, etc.). For a true AcDbCircle, use
# AutoCAD's CIRCLE command instead.
#
# Usage:
#   pwsh -File add_circle_polyline.ps1 -CenterX 0 -CenterY 0 -Radius 0.0224 -Vertices 500
#
# Optional:
#   -Layer       layer to assign (default: current active layer)
#   -StartAngle  starting math angle in degrees (default 0 = +X axis)
#   -Document    name substring / index when multiple docs are open

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][double]$CenterX,
    [Parameter(Mandatory=$true)][double]$CenterY,
    [Parameter(Mandatory=$true)][double]$Radius,
    [Parameter(Mandatory=$true)][int]$Vertices,
    [string]$Layer,
    [double]$StartAngle = 0.0,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"

if ($Vertices -lt 3) { throw "Vertices must be >= 3 (got $Vertices)." }
if ($Radius -le 0)   { throw "Radius must be positive (got $Radius)." }

$doc = Connect-AutoCAD -Document $Document
$ms  = $doc.ModelSpace

$arr = New-Object 'double[]' ($Vertices * 2)
$startRad = $StartAngle * [Math]::PI / 180.0
for ($i = 0; $i -lt $Vertices; $i++) {
    $a = $startRad + 2.0 * [Math]::PI * $i / $Vertices
    $arr[2*$i]     = $CenterX + $Radius * [Math]::Cos($a)
    $arr[2*$i + 1] = $CenterY + $Radius * [Math]::Sin($a)
}
$pl = $ms.AddLightWeightPolyline($arr)
$pl.Closed = $true
if ($Layer) { $pl.Layer = $Layer }

# Area diagnostic: polygon area vs the true circle of the same radius.
# Regular polygon area = 0.5 * n * r^2 * sin(2*pi/n).
$polyArea = 0.5 * $Vertices * $Radius * $Radius * [Math]::Sin(2.0 * [Math]::PI / $Vertices)
$circleArea = [Math]::PI * $Radius * $Radius
$pctOfCircle = 100.0 * $polyArea / $circleArea

"---- Closed polyline circle ----"
"  Handle:    $($pl.Handle)"
"  Layer:     $($pl.Layer)"
"  Vertices:  $Vertices"
"  Center:    ($CenterX, $CenterY)"
"  Radius:    $Radius"
"  Area (CAD): {0:E4} sq units" -f $pl.Area
"  Area (formula): {0:E4} sq units" -f $polyArea
"  True circle:    {0:E4} sq units" -f $circleArea
"  Polygon area as % of true circle: {0:F4}%" -f $pctOfCircle
""
"Drawing not saved."
