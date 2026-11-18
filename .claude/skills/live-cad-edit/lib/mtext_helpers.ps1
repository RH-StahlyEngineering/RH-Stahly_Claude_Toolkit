# live-cad-edit / lib / mtext_helpers.ps1
#
# MTEXT creation helpers shared across the skill. See
# references/mtext_creation.md for the full convention notes.

function Get-AnnoScaleFactor {
    <#
    .SYNOPSIS
      Parse a CANNOSCALE string ("1\" = 1000'", "1:1000", etc.) into a numeric scale factor.
    .OUTPUTS
      [double] -- the scale denominator. E.g. "1\" = 1000'" -> 1000.
    #>
    param([Parameter(Mandatory)][string]$ScaleName)

    # Imperial: 1" = 1000'  /  1"=100'  /  1"= 500'
    if ($ScaleName -match '1\s*["'']?\s*=\s*(\d+(?:\.\d+)?)\s*[''"]?') {
        return [double]$Matches[1]
    }
    # Metric / unitless: 1:1000
    if ($ScaleName -match '1\s*:\s*(\d+(?:\.\d+)?)') {
        return [double]$Matches[1]
    }
    throw "Cannot parse CANNOSCALE '$ScaleName' as a numeric scale factor."
}

function Bearing-To-Rotation {
    <#
    .SYNOPSIS
      Convert a surveyor bearing (DMS in any quadrant) to an AutoCAD MText rotation
      in radians (CCW from +X) such that text reads "upward" along the line.
    .PARAMETER Bearing
      Bearing string parseable by Parse-Bearing (see bearing_math.ps1).
    .DESCRIPTION
      For N..W and S..E (NW/SE pointing lines):  rotation = pi/2 + bearing_rad
      For N..E and S..W (NE/SW pointing lines):  rotation = pi/2 - bearing_rad
    #>
    param([Parameter(Mandatory)][string]$Bearing)
    . "$PSScriptRoot\bearing_math.ps1"
    $b = Parse-Bearing -Text $Bearing
    $brad = $b.deg * [Math]::PI / 180.0
    $isNW_SE = (($b.ns -eq 'N' -and $b.ew -eq 'W') -or ($b.ns -eq 'S' -and $b.ew -eq 'E'))
    if ($isNW_SE) {
        return [Math]::PI / 2.0 + $brad
    } else {
        return [Math]::PI / 2.0 - $brad
    }
}

function Ensure-Layer {
    <#
    .SYNOPSIS
      Return the named layer, creating it if missing.
    #>
    param([Parameter(Mandatory)]$Doc, [Parameter(Mandatory)][string]$Name)
    try   { return $Doc.Layers.Item($Name) }
    catch { return $Doc.Layers.Add($Name) }
}

function Add-AnnotativeMText {
    <#
    .SYNOPSIS
      Create an annotative MText at the given insertion point with the named
      annotative style. Handles CANNOSCALE save/set/restore so the current
      annotation scale is captured on the object.
    .PARAMETER Doc
      The AcadDocument.
    .PARAMETER InsertX, InsertY
      Insertion point coords.
    .PARAMETER Content
      MText content string, with escape codes (see mtext_creation.md).
    .PARAMETER StyleName
      Annotative style name. The style MUST be annotative (named "Annotative *"
      in this drawing). The skill cannot toggle .Annotative via COM on this
      AutoCAD build, so the style is the lever.

      IMPORTANT: The numeric suffix in a style name like "Annotative Italic-0.08"
      is *decorative*. The same style can render at any paper height -- the
      paper height is set per-MText via PaperHeight, not by the style. Stahly
      reuses "Annotative Italic-0.08" at paper heights 0.08, 0.10, etc.
    .PARAMETER LayerName
      Layer to assign. Created if missing.
    .PARAMETER RotationRad
      Rotation in radians (CCW from +X axis).
    .PARAMETER PaperHeight
      Plotted text height in inches (e.g. 0.08, 0.10). Combined with the target
      annotation scale to compute model-units height.
    .PARAMETER AnnoScaleName
      CANNOSCALE name to apply (e.g. "1\" = 1000'"). If supplied AND the scale
      is registered in the drawing's scale list, the MText is created at that
      annotation scale. If the name is NOT registered, the function falls back
      to parsing the factor from the name (e.g. "1\" = 100'" -> 100) for
      height computation, but the MText's annotation-scale list will NOT
      include this name -- the user must add it manually via SCALELISTEDIT +
      OBJECTSCALE. The function emits a Write-Warning in the fallback case.
    .PARAMETER AnnoScaleFactor
      Explicit numeric scale factor (e.g. 100 for 1\"=100', 1000 for 1\"=1000').
      Use this when the scale isn't registered in the drawing OR to bypass
      name-parsing entirely. Overrides any factor derivable from AnnoScaleName.
    .PARAMETER BoxWidth
      MText bounding-box width in model units. Default = 30x the model height
      (generous; keeps record-label single-line for ~30 italic chars).
    .PARAMETER AttachmentPoint
      MText attachment-point code:
        1=TL  2=TC  3=TR  4=ML  5=MC  6=MR  7=BL  8=BC  9=BR
      Default is 5 (middle-center) so the visual center of the text sits at
      the supplied insertion point regardless of box width. This is the
      Stahly record-label convention.
    .OUTPUTS
      The AcadMText COM object.
    #>
    param(
        [Parameter(Mandatory)]$Doc,
        [Parameter(Mandatory)][double]$InsertX,
        [Parameter(Mandatory)][double]$InsertY,
        [Parameter(Mandatory)][string]$Content,
        [Parameter(Mandatory)][string]$StyleName,
        [Parameter(Mandatory)][string]$LayerName,
        [Parameter(Mandatory)][double]$RotationRad,
        [Parameter(Mandatory)][double]$PaperHeight,
        [string]$AnnoScaleName,
        [double]$AnnoScaleFactor = 0,
        [double]$BoxWidth = 0.0,
        [int]$AttachmentPoint = 5
    )

    Ensure-Layer -Doc $Doc -Name $LayerName | Out-Null

    # Save current CANNOSCALE.
    $origScale = $null
    try { $origScale = $Doc.GetVariable('CANNOSCALE') } catch {}

    # Try to apply the requested scale name to CANNOSCALE. If the name isn't
    # registered, fall back gracefully.
    $scaleAssigned = $false
    if ($AnnoScaleName) {
        try {
            $Doc.SetVariable('CANNOSCALE', $AnnoScaleName)
            $scaleAssigned = $true
        } catch {
            Write-Warning ("CANNOSCALE '{0}' is not registered in this drawing's scale list. " +
                "The MText height will be computed from the parsed (or supplied) factor, " +
                "but the resulting MText's annotation-scale list will not include this name. " +
                "To assign the scale: SCALELISTEDIT (add '{0}'), then OBJECTSCALE (add it to the new MText)." -f $AnnoScaleName)
        }
    }

    # Determine scale factor: explicit override > parsed from name > parsed from current CANNOSCALE.
    if ($AnnoScaleFactor -gt 0) {
        $scaleFactor = $AnnoScaleFactor
    } else {
        $effectiveScale = $AnnoScaleName
        if (-not $effectiveScale) { $effectiveScale = $origScale }
        $scaleFactor = Get-AnnoScaleFactor -ScaleName $effectiveScale
    }
    $modelHeight = $PaperHeight * $scaleFactor

    if ($BoxWidth -le 0) { $BoxWidth = $modelHeight * 30.0 }

    $ip = New-Object 'double[]' 3
    $ip[0] = $InsertX; $ip[1] = $InsertY; $ip[2] = 0.0

    $mt = $Doc.ModelSpace.AddMText($ip, $BoxWidth, $Content)
    # Set StyleName FIRST so it doesn't clobber Height set later.
    $mt.StyleName = $StyleName
    $mt.Layer     = $LayerName
    $mt.Height    = $modelHeight
    $mt.Rotation  = $RotationRad
    # AttachmentPoint resets InsertionPoint -- set it then re-anchor.
    try {
        $mt.AttachmentPoint = $AttachmentPoint
        $mt.InsertionPoint  = $ip
    } catch {}

    # Restore CANNOSCALE so we don't perturb the user's working scale.
    if ($scaleAssigned -and $origScale -and $origScale -ne $AnnoScaleName) {
        try { $Doc.SetVariable('CANNOSCALE', $origScale) } catch {}
    }

    return $mt
}

function Get-LineByHandle {
    <#
    .SYNOPSIS
      Look up an AcDbLine by hex handle. Throws if missing or wrong type.
    #>
    param([Parameter(Mandatory)]$Doc, [Parameter(Mandatory)][string]$Handle)
    try   { $obj = $Doc.HandleToObject($Handle) }
    catch { throw "No entity with handle '$Handle' in document '$($Doc.Name)'." }
    if ($obj.ObjectName -ne 'AcDbLine') {
        throw "Handle '$Handle' is a $($obj.ObjectName), not AcDbLine."
    }
    return $obj
}

function Find-MTextByContent {
    <#
    .SYNOPSIS
      Search every layout (model space + every paper-space layout) for MText
      whose TextString matches a regex pattern. Returns an array of objects with
      the matched MText's handle, layout name, and a content preview.
    .DESCRIPTION
      Use this when an MText's handle is no longer known (entity moved between
      model and paper space, regenerated, replaced via copy/move) but you can
      identify it by content.
    .PARAMETER Doc
      The AcadDocument.
    .PARAMETER Pattern
      Regex pattern, e.g. 'BEING TRACT 1', '20__', '\\T0\.85;'.
    .PARAMETER IncludeMLeader
      Also include AcDbMLeader / multileader-derived classes (default $true).
    .OUTPUTS
      Array of PSCustomObject: { Handle, Layout, ObjectName, Layer, Preview }
    #>
    param(
        [Parameter(Mandatory)]$Doc,
        [Parameter(Mandatory)][string]$Pattern,
        [switch]$IncludeMLeader = $true
    )
    $results = @()
    foreach ($lay in $Doc.Layouts) {
        $blk = $lay.Block
        foreach ($e in $blk) {
            $on = $e.ObjectName
            $isMText  = $on -eq 'AcDbMText'
            $isMLead  = $IncludeMLeader -and ($on -match 'MLeader|MultiLeader')
            if (-not ($isMText -or $isMLead)) { continue }
            $t = $null
            try { $t = $e.TextString } catch { continue }
            if ($t -and $t -match $Pattern) {
                $preview = ($t -replace "\\P|\r|\n", ' / ')
                if ($preview.Length -gt 120) { $preview = $preview.Substring(0, 120) }
                $results += [pscustomobject]@{
                    Handle     = $e.Handle
                    Layout     = $lay.Name
                    ObjectName = $on
                    Layer      = $e.Layer
                    Preview    = $preview
                }
            }
        }
    }
    return $results
}

function Set-EntityY {
    <#
    .SYNOPSIS
      Set an MText / MLeader insertion-point Y while preserving X, Z, and every
      other property (style, width, attachment, layer, content). The surgical
      vertical-move primitive for paper-space layout work.
    .PARAMETER Doc
      The AcadDocument.
    .PARAMETER Handle
      Hex entity handle.
    .PARAMETER NewY
      Target Y in drawing units. For paper space, that's paper inches.
    .OUTPUTS
      PSCustomObject { Handle, OldY, NewY, Delta }
    #>
    param(
        [Parameter(Mandatory)]$Doc,
        [Parameter(Mandatory)][string]$Handle,
        [Parameter(Mandatory)][double]$NewY
    )
    $e = $Doc.HandleToObject($Handle)
    $ip = $e.InsertionPoint
    $oldY = $ip[1]
    $newIp = New-Object 'double[]' 3
    $newIp[0] = $ip[0]; $newIp[1] = $NewY; $newIp[2] = $ip[2]
    $e.InsertionPoint = $newIp
    return [pscustomobject]@{ Handle=$Handle; OldY=$oldY; NewY=$NewY; Delta=($NewY - $oldY) }
}

function Set-EntityX {
    <#
    .SYNOPSIS
      Set an MText / MLeader insertion-point X while preserving Y, Z, and every
      other property. The horizontal-alignment primitive.
    #>
    param(
        [Parameter(Mandatory)]$Doc,
        [Parameter(Mandatory)][string]$Handle,
        [Parameter(Mandatory)][double]$NewX
    )
    $e = $Doc.HandleToObject($Handle)
    $ip = $e.InsertionPoint
    $oldX = $ip[0]
    $newIp = New-Object 'double[]' 3
    $newIp[0] = $NewX; $newIp[1] = $ip[1]; $newIp[2] = $ip[2]
    $e.InsertionPoint = $newIp
    return [pscustomobject]@{ Handle=$Handle; OldX=$oldX; NewX=$NewX; Delta=($NewX - $oldX) }
}

function Get-MTextContentHeight {
    <#
    .SYNOPSIS
      Robust MText content-height measurement that returns both the bounding-box
      reading and a paragraph-count-based estimate, plus a "trust" verdict.
    .DESCRIPTION
      GetBoundingBox on AcadMText is unreliable in two specific ways:

      1) **Broken bbox.** Some MText with leading paragraph-format codes
         (`\pxql;`), or with title-block patterns like `{\LTitle\P}(subtitle)`,
         report a degenerate bbox (just the height of the first line, or even
         0). Symptom: returned bbox height much smaller than (paragraphs ×
         LineSpacingDistance).

      2) **Stretched box.** A user can manually grip-stretch the MText vertical
         extent past where the content actually ends. The bbox then reports the
         BOX height, not the content height. Symptom: returned bbox height much
         larger than (paragraphs × LineSpacingDistance).

      This helper returns the bbox value, a manual estimate from paragraph
      count, and a flag noting which case (if any) likely applies. When in
      doubt, ASK the user — they can read it off the AutoCAD Properties palette
      in seconds.

      The manual estimate assumes no word wrap. For text with long paragraphs
      and a narrow Width, the estimate will under-report. For text without
      wrap, the two values should agree within ~10%.
    .PARAMETER Doc
      The AcadDocument.
    .PARAMETER Handle
      Hex MText handle.
    .OUTPUTS
      PSCustomObject {
        BBoxHeight       (double, what GetBoundingBox returned)
        EstimateNoWrap   (double, paragraphs × LineSpacingDistance)
        Paragraphs       (int, count of \P-delimited segments after trimming trailing \P)
        Verdict          (string: 'OK', 'BBoxLooksBroken', 'BoxLooksStretched', or 'BBoxUnusable')
        Recommend        (string: a one-line action)
      }
    #>
    param(
        [Parameter(Mandatory)]$Doc,
        [Parameter(Mandatory)][string]$Handle
    )
    $mt = $Doc.HandleToObject($Handle)
    $min = $null; $max = $null
    try { $mt.GetBoundingBox([ref]$min, [ref]$max) } catch {}
    $bbH = if ($null -ne $max -and $null -ne $min) { [double]($max[1] - $min[1]) } else { 0.0 }

    $t = $mt.TextString
    if (-not $t) {
        return [pscustomobject]@{
            BBoxHeight=$bbH; EstimateNoWrap=0.0; Paragraphs=0
            Verdict='BBoxUnusable'; Recommend='Empty TextString; check entity'
        }
    }
    $tTrim = $t -replace '(\\P\s*)+$', ''
    $paras = ($tTrim -split '\\P').Count
    $lsd = $mt.LineSpacingDistance
    $estimate = $paras * $lsd

    # Verdict
    $verdict = 'OK'
    $reco    = "BBox $('{0:F4}' -f $bbH) in matches paragraph-count estimate $('{0:F4}' -f $estimate) in (no wrap)"
    if ($bbH -lt 0.5 * $estimate -or $bbH -lt $lsd) {
        $verdict = 'BBoxLooksBroken'
        $reco    = "BBox $('{0:F4}' -f $bbH) << estimate $('{0:F4}' -f $estimate); leading paragraph code (e.g. \pxql;) likely confusing GetBoundingBox. Ask user for height."
    } elseif ($bbH -gt 2.0 * $estimate -and $bbH -gt 0.5) {
        $verdict = 'BoxLooksStretched'
        $reco    = "BBox $('{0:F4}' -f $bbH) >> estimate $('{0:F4}' -f $estimate); MText box was manually grip-stretched past content. Have user minimize the box (or supply actual visible content height)."
    }

    return [pscustomobject]@{
        BBoxHeight     = $bbH
        EstimateNoWrap = $estimate
        Paragraphs     = $paras
        Verdict        = $verdict
        Recommend      = $reco
    }
}

function Compute-EqualSpacedColumn {
    <#
    .SYNOPSIS
      Compute Y positions for a vertical column of items with equal gaps and
      configurable margins, honoring a "minimum gap above" constraint at any
      index (e.g. signature line ≥ 1 inch above).
    .DESCRIPTION
      Solves the layout where:
        - all gaps between adjacent items are equal (call it G)
        - top margin (from TopBound to top of first item) = TopFactor × G
        - bottom margin = BottomFactor × G
        - the gap above $MinGapAboveIndex (0-based) is at least $MinGapAbove
        - everything fits between TopBound (high Y) and BottomBound (low Y)

      With TopFactor=0 BottomFactor=1 ("keep top item fixed, add bottom margin
      = gap"), TopBound = current top Y of first item.

      With TopFactor=1 BottomFactor=1 ("equal spacing everywhere"), TopBound =
      the actual upper boundary feature (header, etc.).

      With TopFactor=0 BottomFactor=0 ("top fixed, bottom touches bound"),
      bottom item ends exactly at BottomBound. (No bottom margin.)
    .PARAMETER TopBound
      Upper Y bound. Top of the first item lands at TopBound − TopFactor × G.
    .PARAMETER BottomBound
      Lower Y bound. Bottom of the last item lands at BottomBound + BottomFactor × G.
    .PARAMETER ItemHeights
      Array of heights, in column order (index 0 = topmost).
    .PARAMETER MinGapAboveIndex
      Optional 0-based index of the item that must have ≥ MinGapAbove inches
      above. Use -1 (default) for no constraint.
    .PARAMETER MinGapAbove
      Required minimum gap above MinGapAboveIndex item. Default 1.0.
    .PARAMETER TopFactor
      Multiplier on G for the top margin. Default 1.0.
    .PARAMETER BottomFactor
      Multiplier on G for the bottom margin. Default 1.0.
    .OUTPUTS
      PSCustomObject {
        Gap         (double, the computed equal gap)
        TopYs       (double[], top Y for each item in input order)
        TopMargin   (double, TopBound − TopYs[0])
        BottomMargin(double, BottomYs[last] − BottomBound)
        Feasible    (bool, false if the layout doesn't fit with G ≥ 0 or the
                     min-gap constraint can't be satisfied without violating
                     equal-gap rule)
        Notes       (string[], explanatory diagnostics)
      }
    #>
    param(
        [Parameter(Mandatory)][double]$TopBound,
        [Parameter(Mandatory)][double]$BottomBound,
        [Parameter(Mandatory)][double[]]$ItemHeights,
        [int]$MinGapAboveIndex = -1,
        [double]$MinGapAbove = 1.0,
        [double]$TopFactor = 1.0,
        [double]$BottomFactor = 1.0
    )
    $n = $ItemHeights.Length
    if ($n -lt 1) { throw "Need at least one item" }
    $available = $TopBound - $BottomBound
    $contentSum = ($ItemHeights | Measure-Object -Sum).Sum
    $nGaps = $n - 1
    # available = TopFactor*G + content + nGaps*G + BottomFactor*G
    # available - content = (TopFactor + nGaps + BottomFactor) * G
    $divisor = $TopFactor + $nGaps + $BottomFactor
    if ($divisor -le 0) { throw "Need at least one space (gap or margin)" }
    $G = ($available - $contentSum) / $divisor
    $notes = @()
    $feasible = $true
    if ($G -lt 0) {
        $notes += "Content exceeds available space; gap would be $('{0:F4}' -f $G) (negative)."
        $feasible = $false
    }
    if ($MinGapAboveIndex -ge 0 -and $G -lt $MinGapAbove) {
        $notes += "Equal gap $('{0:F4}' -f $G) is below MinGapAbove $MinGapAbove for item index $MinGapAboveIndex."
        $feasible = $false
    }
    # Compute top Ys
    $tops = New-Object 'double[]' $n
    $tops[0] = $TopBound - $TopFactor * $G
    for ($i = 1; $i -lt $n; $i++) {
        $tops[$i] = $tops[$i-1] - $ItemHeights[$i-1] - $G
    }
    $bottomY = $tops[$n-1] - $ItemHeights[$n-1]
    $topMargin = $TopBound - $tops[0]
    $bottomMargin = $bottomY - $BottomBound
    return [pscustomobject]@{
        Gap          = $G
        TopYs        = $tops
        TopMargin    = $topMargin
        BottomMargin = $bottomMargin
        Feasible     = $feasible
        Notes        = $notes
    }
}

function Expand-UnderscoreTracking {
    <#
    .SYNOPSIS
      Wrap every run of two or more underscores in `{\T<factor>;...}` tracking
      blocks, with the underscore count multiplied by 1/factor (rounded) so the
      visible length is preserved while the gaps close.
    .DESCRIPTION
      Stahly plat-certificate fill-in lines (CCR labels, signature/date/year
      blanks) use the `\T0.85;` tracking convention to make the underscore run
      look like a solid line. Use this to convert default-tracking underscore
      runs into the compressed form en masse.

      Idempotent: runs already inside `{\T...;_______}` blocks are not touched
      (the leading `{\T` makes them no longer pure underscore runs to the
      outer regex).
    .PARAMETER Text
      Source MText content string.
    .PARAMETER Factor
      Tracking factor. Default 0.85 (Stahly convention). Must be > 0 and < 1
      for the expansion math to make sense; out-of-range values still work but
      the expansion may shrink the count.
    .OUTPUTS
      [string] Updated text with underscore runs wrapped.
    #>
    param(
        [Parameter(Mandatory)][string]$Text,
        [double]$Factor = 0.85
    )
    $rx = [regex]'_{2,}'
    return $rx.Replace($Text, {
        param($m)
        $n  = $m.Value.Length
        $m2 = [int][Math]::Round($n / $Factor, [MidpointRounding]::AwayFromZero)
        if ($m2 -lt $n) { $m2 = $n }  # never reduce; safety
        return '{\T' + $Factor + ';' + ('_' * $m2) + '}'
    })
}
