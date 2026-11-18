# live-cad-edit / lib / solvers.ps1
#
# Constraint solvers. All are single-parameter bisections -- robust and
# deterministic. If your problem doesn't fit a 1-D parameterization,
# decompose it manually rather than reaching for nonlinear optimization.

function Solve-Bisection {
    <#
    .SYNOPSIS
      Find a root of f(x) in [Lo, Hi] via bisection. f must change sign.
    .PARAMETER F
      Scriptblock that takes one double and returns a double.
    .PARAMETER Tolerance
      Stop when |f(x)| < this. Default 1e-10.
    .PARAMETER MaxIterations
      Default 200.
    #>
    param(
        [Parameter(Mandatory=$true)][scriptblock]$F,
        [Parameter(Mandatory=$true)][double]$Lo,
        [Parameter(Mandatory=$true)][double]$Hi,
        [double]$Tolerance = 1e-10,
        [int]$MaxIterations = 200
    )
    $fLo = & $F $Lo
    $fHi = & $F $Hi
    if ($fLo * $fHi -gt 0) {
        throw "Bisection cannot bracket a root in [$Lo, $Hi]: f(Lo) = $fLo, f(Hi) = $fHi. Widen the bracket or check the constraint."
    }
    for ($i = 0; $i -lt $MaxIterations; $i++) {
        $mid = ($Lo + $Hi) / 2.0
        $fMid = & $F $mid
        if ([Math]::Abs($fMid) -lt $Tolerance) { return $mid }
        if ($fLo * $fMid -lt 0) { $Hi = $mid; $fHi = $fMid }
        else                    { $Lo = $mid; $fLo = $fMid }
    }
    return ($Lo + $Hi) / 2.0
}

function Solve-PerpShift-ForArea {
    <#
    .SYNOPSIS
      "Hold all bearings; move the polyline's segment between two named
       vertices perpendicular to itself; hit a target area exactly."
    .DESCRIPTION
      The moved segment slides parallel to itself by perpendicular distance d.
      Both endpoints of the segment slide along their adjacent courses
      (whose directions are preserved). The amount each endpoint moves along
      its adjacent course is d / (u_adj · n_seg).
    .PARAMETER X, Y
      Current polyline vertex coords (double[] parallel arrays).
    .PARAMETER VaIdx, VbIdx
      0-based indices of the two endpoints of the segment to shift.
      Va is the "earlier" vertex (smaller polyline index) and Vb the later;
      Va is preceded by V(Va-1) which provides the adjacent course bearing,
      and Vb is followed by V(Vb+1) which provides the other adjacent course.
    .PARAMETER TargetArea
      Target area in square feet.
    .OUTPUTS
      Hashtable: D (perp shift in ft), NewX, NewY (full new vertex arrays
      with Va and Vb moved), FinalArea, Residual.
    #>
    param(
        [Parameter(Mandatory=$true)][double[]]$X,
        [Parameter(Mandatory=$true)][double[]]$Y,
        [Parameter(Mandatory=$true)][int]$VaIdx,
        [Parameter(Mandatory=$true)][int]$VbIdx,
        [Parameter(Mandatory=$true)][double]$TargetArea
    )
    . "$PSScriptRoot\geometry.ps1"

    $n = $X.Length
    if ((($VaIdx + 1) % $n) -ne $VbIdx) {
        throw "VaIdx ($VaIdx) and VbIdx ($VbIdx) must be consecutive in polyline order."
    }
    $iPrev = ($VaIdx - 1 + $n) % $n
    $iNext = ($VbIdx + 1) % $n

    # Unit vectors of the three relevant courses
    $u12 = Unit-Vector ($X[$VaIdx] - $X[$iPrev]) ($Y[$VaIdx] - $Y[$iPrev])
    $u13 = Unit-Vector ($X[$VbIdx] - $X[$VaIdx]) ($Y[$VbIdx] - $Y[$VaIdx])
    $u14 = Unit-Vector ($X[$iNext] - $X[$VbIdx]) ($Y[$iNext] - $Y[$VbIdx])
    $u14r = @{ ux = -$u14.ux; uy = -$u14.uy }

    # Normal to the shifted segment; pick the half-plane with +X
    $n13x = -$u13.uy; $n13y = $u13.ux
    if ($n13x -lt 0) { $n13x = -$n13x; $n13y = -$n13y }

    $k1 = $u12.ux * $n13x + $u12.uy * $n13y
    $k2 = $u14r.ux * $n13x + $u14r.uy * $n13y
    if ([Math]::Abs($k1) -lt 1e-12 -or [Math]::Abs($k2) -lt 1e-12) {
        throw "Adjacent course is parallel to the segment being shifted -- degenerate."
    }

    # Compute area as function of d
    $X0 = $X[$VaIdx]; $Y0 = $Y[$VaIdx]
    $X1 = $X[$VbIdx]; $Y1 = $Y[$VbIdx]
    $script:bs_X = $X.Clone()
    $script:bs_Y = $Y.Clone()
    $script:bs_Va = $VaIdx; $script:bs_Vb = $VbIdx
    $script:bs_X0 = $X0; $script:bs_Y0 = $Y0
    $script:bs_X1 = $X1; $script:bs_Y1 = $Y1
    $script:bs_u12x = $u12.ux; $script:bs_u12y = $u12.uy
    $script:bs_u14rx = $u14r.ux; $script:bs_u14ry = $u14r.uy
    $script:bs_k1 = $k1; $script:bs_k2 = $k2

    $areaFn = {
        param([double]$d)
        $da = $d / $script:bs_k1
        $db = $d / $script:bs_k2
        $script:bs_X[$script:bs_Va] = $script:bs_X0 + $da * $script:bs_u12x
        $script:bs_Y[$script:bs_Va] = $script:bs_Y0 + $da * $script:bs_u12y
        $script:bs_X[$script:bs_Vb] = $script:bs_X1 + $db * $script:bs_u14rx
        $script:bs_Y[$script:bs_Vb] = $script:bs_Y1 + $db * $script:bs_u14ry
        Shoelace-Area $script:bs_X $script:bs_Y
    }
    $f = { param($d) (& $areaFn $d) - $TargetArea }

    # Bracket: start broad
    $dSolved = Solve-Bisection -F $f -Lo -500.0 -Hi 500.0
    $finalArea = & $areaFn $dSolved
    return @{
        D = $dSolved
        NewX = $script:bs_X.Clone()
        NewY = $script:bs_Y.Clone()
        FinalArea = $finalArea
        Residual = $finalArea - $TargetArea
        NewVaX = $script:bs_X[$VaIdx]; NewVaY = $script:bs_Y[$VaIdx]
        NewVbX = $script:bs_X[$VbIdx]; NewVbY = $script:bs_Y[$VbIdx]
    }
}

function Solve-BearingIntersection {
    <#
    .SYNOPSIS
      Place a new vertex at the intersection of (line from FixedX/FixedY
      in direction Ubrg) AND (a reference line offset by perpendicular
      distance Dist from RefAx/RefAy -> RefBx/RefBy).
    .DESCRIPTION
      Common use: rotate a parcel segment to a target bearing while keeping
      the segment's other endpoint exactly on a (e.g. 60-ft) offset of a
      section / ROW line.
    .PARAMETER Side
      +1 if the offset is on the right of Ref-A->Ref-B (often south of an
      east-running line); -1 if on the left.
    .OUTPUTS
      Hashtable X, Y of the new vertex.
    #>
    param(
        [double]$FixedX, [double]$FixedY,
        [double]$Ubrgx, [double]$Ubrgy,
        [double]$RefAx, [double]$RefAy,
        [double]$RefBx, [double]$RefBy,
        [double]$Dist,
        [int]$Side = 1
    )
    . "$PSScriptRoot\geometry.ps1"
    $off = Offset-Line -ax $RefAx -ay $RefAy -bx $RefBx -by $RefBy -Dist $Dist -Side $Side
    $hit = Intersect-Lines $FixedX $FixedY $Ubrgx $Ubrgy $off.X $off.Y $off.ux $off.uy
    if ($null -eq $hit) {
        throw "Solve-BearingIntersection: target bearing line is parallel to the offset line; no unique intersection."
    }
    return @{ X = $hit.X; Y = $hit.Y; S = $hit.s; T = $hit.t }
}
