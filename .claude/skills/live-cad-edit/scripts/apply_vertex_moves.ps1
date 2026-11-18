# live-cad-edit / scripts / apply_vertex_moves.ps1
#
# Apply a batch of vertex moves to one or more LWPolylines via COM.
# Accepts an array of "moves" each specifying handle, 1-based vertex index,
# and target X/Y.
#
# Verifies after applying by re-pulling vertices and reporting the actual
# new positions and the actual new area of each touched polyline.
#
# Does NOT save the drawing. User saves manually in AutoCAD.
#
# INPUT SHAPE: -Moves expects a PowerShell array of hashtables. Each hashtable
# must have FOUR keys -- spelled exactly:
#   Handle (string)  -- the AcDbPolyline hex handle
#   Vertex (int)     -- 1-based vertex index (matches what mapcheck.ps1 prints)
#   X (double)       -- target X in drawing units (US Survey Feet, typically)
#   Y (double)       -- target Y in drawing units
#
# Do NOT pass JSON; pass PowerShell hashtables. Example:
#
#   pwsh -File apply_vertex_moves.ps1 -Moves @(
#       @{Handle='15053'; Vertex=8;  X=2366756.0072; Y=1005708.3437},
#       @{Handle='15053'; Vertex=9;  X=2367374.7394; Y=1005731.2005},
#       @{Handle='1583E'; Vertex=15; X=2366756.0072; Y=1005708.3437},
#       @{Handle='1583E'; Vertex=14; X=2367374.7394; Y=1005731.2005}
#   )
#
# Group multiple polylines into the same -Moves call -- the script handles
# coordinated topology updates that way (e.g. moving a shared vertex on both
# the 20-ac and the adjoining 170-ac in one run).

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][hashtable[]]$Moves,
    [string]$Document
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\lib\com_bootstrap.ps1"
. "$PSScriptRoot\..\lib\geometry.ps1"

$doc = Connect-AutoCAD -Document $Document

# Group moves by handle so we touch each polyline once per move (still applies
# one vertex at a time via Set-PolylineVertex -- but we cache the polyline
# object lookup).
$byHandle = @{}
foreach ($m in $Moves) {
    if (-not $byHandle.ContainsKey($m.Handle)) { $byHandle[$m.Handle] = @() }
    $byHandle[$m.Handle] += $m
}

$results = @()
foreach ($h in $byHandle.Keys) {
    $pl = Get-PolylineByHandle -Doc $doc -Handle $h
    "Updating polyline $h..."
    foreach ($m in $byHandle[$h]) {
        $idx0 = [int]$m.Vertex - 1
        $r = Set-PolylineVertex -Polyline $pl -Index $idx0 -NewX ([double]$m.X) -NewY ([double]$m.Y)
        "  v{0,-2}: ({1:F4},{2:F4}) -> ({3:F4},{4:F4})   shift {5:F4} ft" -f $m.Vertex, $r.OldX, $r.OldY, $r.NewX, $r.NewY, $r.Shift
        $results += [pscustomobject]@{
            Handle = $h; Vertex = $m.Vertex
            OldX = $r.OldX; OldY = $r.OldY
            NewX = $r.NewX; NewY = $r.NewY
            Shift = $r.Shift
        }
    }
    $newArea = $pl.Area
    "  -> new area: {0:N4} sq ft  ({1:F6} ac)" -f $newArea, ($newArea / 43560.0)
    ""
}

"================================================================"
"All moves applied. Drawing is NOT saved -- review in AutoCAD and save manually."
"Run scripts\audit_topology.ps1 to confirm topology is still clean."
