# live-cad-edit / lib / bearing_math.ps1
#
# Surveyor's bearing conventions: angle from N/S axis, 0..90 deg, with
# quadrant letter (N/S then E/W). NOT compass azimuth.

function Format-Bearing {
    <#
    .SYNOPSIS
      Format a (dx, dy) displacement as a surveyor's bearing rounded to the nearest second.
    .EXAMPLE
      Format-Bearing -dx -8.5353 -dy 206.5211   # -> "N 02°22'00" W"
    #>
    param(
        [Parameter(Mandatory=$true)][double]$dx,
        [Parameter(Mandatory=$true)][double]$dy,
        [int]$DecimalsOnSec = 0
    )
    $absDx = [Math]::Abs($dx); $absDy = [Math]::Abs($dy)
    if ($absDx -lt 1e-12 -and $absDy -lt 1e-12) { return 'N 00°00''00" E' }
    $rad = [Math]::Atan2($absDx, $absDy)
    $deg = $rad * 180.0 / [Math]::PI

    if ($DecimalsOnSec -le 0) {
        $tot = [Math]::Round($deg * 3600.0)
        $d = [Math]::Floor($tot / 3600.0); $r = $tot - $d*3600.0
        $m = [Math]::Floor($r / 60.0); $s = $r - $m*60.0
        $secFmt = '{0:D2}'
        $secStr = $secFmt -f [int]$s
    } else {
        $scale = [Math]::Pow(10, $DecimalsOnSec)
        $tot = [Math]::Round($deg * 3600.0 * $scale) / $scale
        $d = [Math]::Floor($tot / 3600.0); $r = $tot - $d*3600.0
        $m = [Math]::Floor($r / 60.0); $s = $r - $m*60.0
        $secStr = ('{0:00.' + ('0' * $DecimalsOnSec) + '}') -f $s
    }
    $ns = if ($dy -ge 0) { 'N' } else { 'S' }
    $ew = if ($dx -ge 0) { 'E' } else { 'W' }
    "{0} {1:D2}°{2:D2}'{3}`" {4}" -f $ns, [int]$d, [int]$m, $secStr, $ew
}

function Parse-Bearing {
    <#
    .SYNOPSIS
      Parse a surveyor's bearing string and return a unit-vector (dx, dy).
    .EXAMPLE
      Parse-Bearing 'N 03°04'10.03" W'
      Parse-Bearing 'S89-27-17 W'
    .OUTPUTS
      Hashtable with keys ux, uy, deg (decimal degrees of the offset from N/S axis).
    #>
    param([Parameter(Mandatory=$true)][string]$Text)
    $t = $Text.ToUpper().Trim()
    # Pull quadrant letters off the ends
    $m = [regex]::Match($t, '^\s*([NS])\s*(.+?)\s*([EW])\s*$')
    if (-not $m.Success) {
        throw "Bearing '$Text' does not match the expected 'N <angle> W' / 'S <angle> E' format."
    }
    $ns = $m.Groups[1].Value
    $ew = $m.Groups[3].Value
    $angleStr = $m.Groups[2].Value
    # Extract numbers: degrees, minutes, seconds (last may be decimal)
    $nums = [regex]::Matches($angleStr, '(\d+(?:\.\d+)?)') | ForEach-Object { [double]$_.Value }
    if ($nums.Count -lt 1 -or $nums.Count -gt 3) {
        throw "Could not parse degrees/minutes/seconds out of '$angleStr'."
    }
    $deg = $nums[0]
    if ($nums.Count -ge 2) { $deg += $nums[1] / 60.0 }
    if ($nums.Count -ge 3) { $deg += $nums[2] / 3600.0 }
    $rad = $deg * [Math]::PI / 180.0
    $absDx = [Math]::Sin($rad)
    $absDy = [Math]::Cos($rad)
    $ux = if ($ew -eq 'E') {  $absDx } else { -$absDx }
    $uy = if ($ns -eq 'N') {  $absDy } else { -$absDy }
    return @{ ux = $ux; uy = $uy; deg = $deg; ns = $ns; ew = $ew }
}

function Azimuth-Deg {
    <#
    .SYNOPSIS
      Return clockwise-from-north azimuth in degrees [0, 360).
    .DESCRIPTION
      Useful for comparing bearing differences via modular arithmetic.
    #>
    param([Parameter(Mandatory=$true)][double]$dx, [Parameter(Mandatory=$true)][double]$dy)
    $az = [Math]::Atan2($dx, $dy) * 180.0 / [Math]::PI
    if ($az -lt 0) { $az += 360.0 }
    return $az
}

function Bearing-DiffSeconds {
    <#
    .SYNOPSIS
      Smallest angular difference between two (dx,dy) vectors, treating
      reversed (180° apart) as equivalent. Returns absolute seconds.
    .DESCRIPTION
      Use when comparing shared edges across adjoining parcels --
      opposite winding direction is normal, not a mismatch.
    #>
    param([double]$dx1, [double]$dy1, [double]$dx2, [double]$dy2)
    $a1 = Azimuth-Deg $dx1 $dy1
    $a2 = Azimuth-Deg $dx2 $dy2
    $d = $a1 - $a2
    while ($d -gt 180)  { $d -= 360 }
    while ($d -lt -180) { $d += 360 }
    # Treat 180-apart as zero (opposite-direction same edge)
    if ([Math]::Abs([Math]::Abs($d) - 180) -lt [Math]::Abs($d)) {
        $d = [Math]::Abs($d) - 180
    }
    return [Math]::Abs($d) * 3600.0
}
