# live-cad-edit / scripts / audit_topology.ps1
#
# Topology audit across N parcel polylines. Identifies coincident vertices,
# near-misses (where they probably SHOULD coincide), and shared-edge
# bearing/distance mismatches.
#
# Usage:
#   pwsh -File audit_topology.ps1 -Handles 1583E,15053,156C0

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string[]]$Handles,
    [double]$Tolerance = 0.005,
    [double]$NearMissCap = 2.0,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\bearing_math.ps1"
. "$PSScriptRoot\..\lib\topology.ps1"

$doc = Connect-AutoCAD -Document $Document

# Load each polyline
$data = @{}
foreach ($h in $Handles) {
    $pl = Get-PolylineByHandle -Doc $doc -Handle $h
    Assert-NoBulges -Polyline $pl -Context "topology audit on $h"
    $vx = Get-PolylineVerticesXY -Polyline $pl
    $data[$h] = @{
        Handle = $h
        Layer = $pl.Layer
        N = $vx.N
        X = $vx.X
        Y = $vx.Y
    }
    "Loaded {0}  layer={1}  verts={2}" -f $h, $pl.Layer, $vx.N
}
""

"Coincidence tolerance: {0} ft (~{1:F4} in). Near-misses flagged up to {2} ft." -f $Tolerance, ($Tolerance*12), $NearMissCap
""

$totalIssues = 0
for ($i = 0; $i -lt $Handles.Length; $i++) {
    for ($j = $i + 1; $j -lt $Handles.Length; $j++) {
        $Ha = $Handles[$i]; $Hb = $Handles[$j]
        $Pa = $data[$Ha];   $Pb = $data[$Hb]
        "----- $Ha  <->  $Hb -----"
        $res = Find-CoincidentVertices -Pa $Pa -Pb $Pb -Tol $Tolerance -MaxOff $NearMissCap
        "  Coincident vertex pairs: {0}" -f $res.Coincident.Count
        if ($res.NearMisses.Count -gt 0) {
            "  *** {0} NEAR-MISSES (probably should coincide):" -f $res.NearMisses.Count
            $totalIssues += $res.NearMisses.Count
            foreach ($nm in $res.NearMisses) {
                "    {0} v{1,-2} ({2:F4},{3:F4})  vs  {4} v{5,-2} ({6:F4},{7:F4})  off {8:F4} ft" -f `
                    $Ha, ($nm.ia + 1), $nm.ax, $nm.ay, $Hb, ($nm.ib + 1), $nm.bx, $nm.by, $nm.d
            }
        }

        $mismatches = Audit-SharedEdges -Pa $Pa -Pb $Pb -Coincident $res.Coincident
        if ($mismatches.Count -gt 0) {
            "  *** {0} SHARED-EDGE MISMATCHES:" -f $mismatches.Count
            $totalIssues += $mismatches.Count
            foreach ($m in $mismatches) {
                $aBrg = Format-Bearing -dx $m.Pa_dx -dy $m.Pa_dy
                $bBrg = Format-Bearing -dx $m.Pb_dx -dy $m.Pb_dy
                "    {0} L{1}->L{2}  {3}  {4,9:N2} ft   <->   {5} L{6}->L{7}  {8}  {9,9:N2} ft   d_brg={10:F2}sec  d_len={11:+0.00;-0.00;0.00}ft" -f `
                    $Ha, $m.IaFrom, $m.IaTo, $aBrg, $m.Pa_len, `
                    $Hb, $m.IbFrom, $m.IbTo, $bBrg, $m.Pb_len, `
                    $m.BearingDiffSec, $m.LengthDiffFt
            }
        }
        ""
    }
}
"================================================================"
if ($totalIssues -eq 0) { "TOPOLOGY CLEAN -- 0 mismatches across {0} polyline pair(s)." -f ([math]::Round($Handles.Length * ($Handles.Length - 1) / 2)) }
else                    { "TOTAL ISSUES: $totalIssues" }
