# live-cad-edit / lib / geometry.ps1
#
# 2D vector math used across the constraint solvers. All inputs/outputs
# are scalar doubles; no nested arrays.

function Intersect-Lines {
    <#
    .SYNOPSIS
      Intersect two parametric lines: P1 + s*U1 = P2 + t*U2.
    .OUTPUTS
      Hashtable with s, t, X, Y. Returns $null if the lines are parallel.
    #>
    param(
        [double]$p1x, [double]$p1y, [double]$u1x, [double]$u1y,
        [double]$p2x, [double]$p2y, [double]$u2x, [double]$u2y
    )
    $det = $u1x * (-$u2y) - $u1y * (-$u2x)
    if ([Math]::Abs($det) -lt 1e-12) { return $null }
    $rhsX = $p2x - $p1x
    $rhsY = $p2y - $p1y
    $s = ($rhsX * (-$u2y) - $rhsY * (-$u2x)) / $det
    $t = ($u1x * $rhsY - $u1y * $rhsX) / $det
    return @{ s = $s; t = $t; X = $p1x + $s*$u1x; Y = $p1y + $s*$u1y }
}

function PerpDist-PointToLine {
    <#
    .SYNOPSIS
      Absolute perpendicular distance from (px,py) to the infinite line
      through (ax,ay) and (bx,by).
    #>
    param([double]$px, [double]$py, [double]$ax, [double]$ay, [double]$bx, [double]$by)
    $dx = $bx - $ax; $dy = $by - $ay
    $L = [Math]::Sqrt($dx*$dx + $dy*$dy)
    if ($L -lt 1e-12) { throw "Line A->B is degenerate (zero length)." }
    $cross = ($px - $ax) * $dy - ($py - $ay) * $dx
    return [Math]::Abs($cross / $L)
}

function Shoelace-Area {
    <#
    .SYNOPSIS
      Polygon area via the shoelace formula. Returns absolute area.
    .PARAMETER X
      double[] x coordinates of vertices, in polyline order.
    .PARAMETER Y
      double[] y coordinates of vertices, in polyline order.
    #>
    param([double[]]$X, [double[]]$Y)
    $n = $X.Length
    if ($Y.Length -ne $n) { throw "X and Y arrays must be the same length." }
    $sum = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $j = ($i + 1) % $n
        $sum += $X[$i] * $Y[$j] - $X[$j] * $Y[$i]
    }
    return [Math]::Abs($sum) / 2.0
}

function Unit-Vector {
    <#
    .SYNOPSIS
      Normalize (dx,dy) to a unit vector. Returns hashtable {ux, uy, len}.
    #>
    param([double]$dx, [double]$dy)
    $L = [Math]::Sqrt($dx*$dx + $dy*$dy)
    if ($L -lt 1e-12) { throw "Zero-length vector." }
    return @{ ux = $dx / $L; uy = $dy / $L; len = $L }
}

function Offset-Line {
    <#
    .SYNOPSIS
      Compute a line parallel to A-B, offset by perpendicular distance D.
      Side is +1 for "right of A->B direction" (south of an east-running line)
      or -1 for "left of A->B direction" (north of an east-running line).
    .OUTPUTS
      Hashtable with X, Y of an anchor point on the offset line, plus ux, uy
      direction along the offset line (same direction as A->B).
    #>
    param([double]$ax, [double]$ay, [double]$bx, [double]$by, [double]$Dist, [int]$Side = 1)
    $u = Unit-Vector ($bx - $ax) ($by - $ay)
    # Normal to A->B: right-hand normal is (uy, -ux); left is (-uy, ux).
    if ($Side -eq 1) { $nx =  $u.uy; $ny = -$u.ux }
    else             { $nx = -$u.uy; $ny =  $u.ux }
    return @{
        X = $ax + $Dist * $nx
        Y = $ay + $Dist * $ny
        ux = $u.ux
        uy = $u.uy
    }
}
