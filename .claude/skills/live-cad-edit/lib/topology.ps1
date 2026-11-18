# live-cad-edit / lib / topology.ps1
#
# Cross-polyline vertex coincidence and shared-edge verification.

function Find-CoincidentVertices {
    <#
    .SYNOPSIS
      For each vertex in Pa, find the closest vertex in Pb.
    .DESCRIPTION
      Categorize each match as Coincident (d < $Tol), Near-Miss (Tol <= d <= MaxOff),
      or no-match. Returns a hashtable with two arrays of pscustomobjects.
    .PARAMETER Pa
      Hashtable with X (double[]), Y (double[]), N (int).
    .PARAMETER Pb
      Same shape as Pa.
    .PARAMETER Tol
      Coincidence tolerance in feet. Default 0.005 (~1/16 inch).
    .PARAMETER MaxOff
      Max distance to report as a near-miss. Default 2.0 ft.
    #>
    param(
        [Parameter(Mandatory=$true)]$Pa,
        [Parameter(Mandatory=$true)]$Pb,
        [double]$Tol = 0.005,
        [double]$MaxOff = 2.0
    )
    $coincident = @()
    $nearMisses = @()
    for ($ia = 0; $ia -lt $Pa.N; $ia++) {
        $bestIb = -1
        $bestD = [double]::MaxValue
        for ($ib = 0; $ib -lt $Pb.N; $ib++) {
            $dx = $Pa.X[$ia] - $Pb.X[$ib]
            $dy = $Pa.Y[$ia] - $Pb.Y[$ib]
            $d = [Math]::Sqrt($dx*$dx + $dy*$dy)
            if ($d -lt $bestD) { $bestD = $d; $bestIb = $ib }
        }
        $item = [pscustomobject]@{
            ia = $ia; ib = $bestIb; d = $bestD
            ax = $Pa.X[$ia]; ay = $Pa.Y[$ia]
            bx = $Pb.X[$bestIb]; by = $Pb.Y[$bestIb]
        }
        if     ($bestD -lt $Tol)     { $coincident += $item }
        elseif ($bestD -le $MaxOff)  { $nearMisses += $item }
    }
    return @{ Coincident = $coincident; NearMisses = $nearMisses }
}

function Audit-SharedEdges {
    <#
    .SYNOPSIS
      For pairs of consecutive coincident vertices on Pa, verify the same
      edge in Pb has matching bearing/distance (with 180° flip allowed,
      since adjoining parcels wind in opposite directions).
    .PARAMETER Pa, Pb
      Same hashtable shape as Find-CoincidentVertices accepts.
    .PARAMETER Coincident
      Output of Find-CoincidentVertices' .Coincident array.
    .PARAMETER BearingTolSec
      Bearing tolerance in seconds. Default 1.0.
    .PARAMETER LenTolFt
      Length tolerance in feet. Default 0.02.
    .OUTPUTS
      Array of pscustomobject mismatches, each with the edge details.
    #>
    param(
        [Parameter(Mandatory=$true)]$Pa,
        [Parameter(Mandatory=$true)]$Pb,
        [Parameter(Mandatory=$true)][object[]]$Coincident,
        [double]$BearingTolSec = 1.0,
        [double]$LenTolFt = 0.02
    )
    # Index coincident matches by ia for O(1) lookup
    $byIa = @{}
    foreach ($c in $Coincident) { $byIa[$c.ia] = $c }

    $mismatches = @()
    foreach ($ia in ($byIa.Keys | Sort-Object)) {
        $iaNext = ($ia + 1) % $Pa.N
        if (-not $byIa.ContainsKey($iaNext)) { continue }
        $ib1 = $byIa[$ia].ib
        $ib2 = $byIa[$iaNext].ib

        $sameDir     = ((($ib1 + 1) % $Pb.N) -eq $ib2)
        $reversedDir = ((($ib1 - 1 + $Pb.N) % $Pb.N) -eq $ib2)
        if (-not ($sameDir -or $reversedDir)) { continue }

        $aDx = $Pa.X[$iaNext] - $Pa.X[$ia]
        $aDy = $Pa.Y[$iaNext] - $Pa.Y[$ia]
        $aL  = [Math]::Sqrt($aDx*$aDx + $aDy*$aDy)
        # Pb edge in the SAME spatial direction as Pa
        $bDx = $Pb.X[$ib2] - $Pb.X[$ib1]
        $bDy = $Pb.Y[$ib2] - $Pb.Y[$ib1]
        $bL  = [Math]::Sqrt($bDx*$bDx + $bDy*$bDy)

        $aAz = [Math]::Atan2($aDx, $aDy) * 180.0 / [Math]::PI
        $bAz = [Math]::Atan2($bDx, $bDy) * 180.0 / [Math]::PI
        $dAz = $aAz - $bAz
        while ($dAz -gt 180)  { $dAz -= 360 }
        while ($dAz -lt -180) { $dAz += 360 }
        # Treat 180-apart as zero (we already corrected the sign, but be defensive)
        if ([Math]::Abs([Math]::Abs($dAz) - 180) -lt [Math]::Abs($dAz)) {
            $dAz = [Math]::Abs($dAz) - 180
        }
        $dAzSec = [Math]::Abs($dAz) * 3600.0
        $dL = $bL - $aL

        if ($dAzSec -gt $BearingTolSec -or [Math]::Abs($dL) -gt $LenTolFt) {
            $mismatches += [pscustomobject]@{
                IaFrom = $ia + 1; IaTo = $iaNext + 1
                IbFrom = (& { if ($sameDir) { $ib1 + 1 } else { $ib2 + 1 } })
                IbTo   = (& { if ($sameDir) { $ib2 + 1 } else { $ib1 + 1 } })
                Dir = (& { if ($sameDir) { 'same' } else { 'reversed' } })
                BearingDiffSec = $dAzSec
                LengthDiffFt = $dL
                Pa_dx = $aDx; Pa_dy = $aDy; Pa_len = $aL
                Pb_dx = $bDx; Pb_dy = $bDy; Pb_len = $bL
            }
        }
    }
    return $mismatches
}
