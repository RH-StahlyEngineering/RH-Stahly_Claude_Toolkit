# live-cad-edit / lib / com_bootstrap.ps1
#
# Attach to a running AutoCAD instance via the Running Object Table.
# PowerShell 7 dropped [Marshal]::GetActiveObject; we wrap the underlying
# Win32 APIs (oleaut32!GetActiveObject + ole32!CLSIDFromProgID).
#
# Dot-source this file at the top of any script:
#   . "$PSScriptRoot\..\lib\com_bootstrap.ps1"
#   $doc = Connect-AutoCAD

Add-Type -ErrorAction SilentlyContinue -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Rot {
    [DllImport("oleaut32.dll", PreserveSig=false)]
    static extern void GetActiveObject([In] ref Guid rclsid, IntPtr pvReserved, [MarshalAs(UnmanagedType.IUnknown)] out object ppunk);
    [DllImport("ole32.dll", PreserveSig=false)]
    static extern void CLSIDFromProgID([MarshalAs(UnmanagedType.LPWStr)] string lpszProgID, out Guid pclsid);
    public static object Get(string progId) {
        Guid clsid; CLSIDFromProgID(progId, out clsid);
        object obj; GetActiveObject(ref clsid, IntPtr.Zero, out obj); return obj;
    }
}
"@

function Connect-AutoCAD {
    <#
    .SYNOPSIS
      Attach to the running AutoCAD.Application and return one open document.
    .DESCRIPTION
      Returns an AcadDocument from the Documents collection. NOT ActiveDocument --
      ActiveDocument can return an empty document object when AutoCAD focus
      is on a palette or dialog, even with a drawing fully loaded.

      Document selection:
        - If only one document is open, returns it regardless of -Document.
        - If multiple documents are open and -Document is not supplied, throws
          and lists all options so the caller can pick.
        - -Document accepts an integer index (0, 1, 2, ...) OR a case-insensitive
          substring of the document Name. The substring must match exactly one
          document; otherwise throws with the candidate list.
    .OUTPUTS
      AcadDocument COM object. Throws clear error if AutoCAD isn't running,
      no document is open, or the selector is ambiguous.
    #>
    param([string]$Document)

    try {
        $acad = [Rot]::Get('AutoCAD.Application')
    } catch {
        throw "AutoCAD is not running. Start AutoCAD and open the target DWG, then retry."
    }
    $docs = $acad.Documents
    if ($docs.Count -lt 1) {
        throw "AutoCAD is running but no document is open. Open the target DWG, then retry."
    }
    if ($docs.Count -eq 1) {
        return $docs.Item(0)
    }

    # Multiple documents -- a selector is required (or this is an error).
    $listLines = @()
    for ($i = 0; $i -lt $docs.Count; $i++) {
        $d = $docs.Item($i)
        $listLines += ("  [{0}] {1}" -f $i, $d.Name)
    }
    $listText = $listLines -join "`n"

    if ([string]::IsNullOrWhiteSpace($Document)) {
        throw "Multiple AutoCAD documents are open. Specify -Document <index> or -Document <name-substring>:`n$listText"
    }

    # Try integer index first
    $asInt = 0
    if ([int]::TryParse($Document, [ref]$asInt)) {
        if ($asInt -lt 0 -or $asInt -ge $docs.Count) {
            throw "Document index $asInt is out of range. Open documents:`n$listText"
        }
        return $docs.Item($asInt)
    }

    # Otherwise substring-match the Name (case-insensitive)
    $matches = @()
    for ($i = 0; $i -lt $docs.Count; $i++) {
        $d = $docs.Item($i)
        if ($d.Name -like "*$Document*") {
            $matches += @{ Index = $i; Doc = $d; Name = $d.Name }
        }
    }
    if ($matches.Count -eq 0) {
        throw "No open document matches '$Document'. Open documents:`n$listText"
    }
    if ($matches.Count -gt 1) {
        $matchedNames = ($matches | ForEach-Object { "  [{0}] {1}" -f $_.Index, $_.Name }) -join "`n"
        throw "Ambiguous document selector '$Document' matched $($matches.Count):`n$matchedNames"
    }
    return $matches[0].Doc
}

function Invoke-WithComRetry {
    <#
    .SYNOPSIS
      Run a scriptblock that uses COM, retrying on RPC_E_CALL_REJECTED.
    .DESCRIPTION
      When AutoCAD is mid-command, has a dialog open, or is processing user
      input, COM calls fail with HRESULT 0x80010001. This wrapper retries
      a few times with short delays and then surfaces a clear message.
    .PARAMETER ScriptBlock
      The code to execute.
    .PARAMETER MaxRetries
      Default 5.
    .PARAMETER DelayMs
      Default 500ms.
    #>
    param(
        [Parameter(Mandatory=$true)][scriptblock]$ScriptBlock,
        [int]$MaxRetries = 5,
        [int]$DelayMs = 500
    )
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        try {
            return & $ScriptBlock
        } catch {
            $msg = $_.Exception.Message
            if ($msg -match '0x80010001|RPC_E_CALL_REJECTED|Call was rejected by callee') {
                if ($attempt -lt $MaxRetries) {
                    Start-Sleep -Milliseconds $DelayMs
                    continue
                }
                throw "AutoCAD rejected the COM call after $MaxRetries attempts. It is likely running a command, in a grip edit, or has a modal dialog open. Cancel/close that and retry."
            }
            throw
        }
    }
}

function Get-PolylineByHandle {
    <#
    .SYNOPSIS
      Look up an LWPolyline by hex handle (the value shown in AutoCAD's
      Properties palette for any entity).
    .OUTPUTS
      The AcadLWPolyline COM object. Throws if the handle doesn't exist
      or refers to a non-polyline entity.
    #>
    param(
        [Parameter(Mandatory=$true)]$Doc,
        [Parameter(Mandatory=$true)][string]$Handle
    )
    try {
        $obj = Invoke-WithComRetry { $Doc.HandleToObject($Handle) }
    } catch {
        if ($_.Exception.Message -match 'Unknown handle|handle') {
            throw "No entity with handle '$Handle' in document '$($Doc.Name)'."
        }
        throw
    }
    if ($null -eq $obj) {
        throw "No entity with handle '$Handle' in document '$($Doc.Name)'."
    }
    if ($obj.ObjectName -ne 'AcDbPolyline') {
        throw "Handle '$Handle' is a $($obj.ObjectName), not an LWPolyline. This skill works on AcDbPolyline only."
    }
    return $obj
}

function Get-PolylineVerticesXY {
    <#
    .SYNOPSIS
      Read an LWPolyline's vertices into two parallel double[] arrays.
    .DESCRIPTION
      Avoid nested @(@(x,y)) array shapes -- PowerShell unwraps them
      inconsistently. Parallel X/Y arrays are unambiguous.
    .OUTPUTS
      Hashtable with keys X (double[]), Y (double[]), N (int).
    #>
    param([Parameter(Mandatory=$true)]$Polyline)

    # Bulges read separately so that callers can detect curves and refuse.
    $coords = Invoke-WithComRetry { $Polyline.Coordinates }
    $n = $coords.Length / 2
    $X = New-Object 'double[]' $n
    $Y = New-Object 'double[]' $n
    for ($i = 0; $i -lt $n; $i++) {
        $X[$i] = [double]$coords[2*$i]
        $Y[$i] = [double]$coords[2*$i+1]
    }
    return @{ X = $X; Y = $Y; N = $n }
}

function Get-PolylineBulges {
    <#
    .SYNOPSIS
      Return the bulge value at each vertex of the LWPolyline.
    .DESCRIPTION
      Bulge != 0 means the segment after that vertex is an arc.
      v1 of this skill refuses to operate on polylines with any non-zero
      bulge; callers should check Test-AnyBulge first.
    #>
    param([Parameter(Mandatory=$true)]$Polyline)
    $n = ($Polyline.Coordinates).Length / 2
    $B = New-Object 'double[]' $n
    for ($i = 0; $i -lt $n; $i++) {
        $B[$i] = [double](Invoke-WithComRetry { $Polyline.GetBulge($i) })
    }
    return $B
}

function Test-AnyBulge {
    <#
    .SYNOPSIS
      Return $true if any segment of the polyline is an arc.
    .DESCRIPTION
      Use this at the top of any script that doesn't handle bulges (v1).
      Throw with a clear message rather than producing wrong areas/bearings.
    #>
    param([Parameter(Mandatory=$true)]$Polyline)
    $bulges = Get-PolylineBulges -Polyline $Polyline
    foreach ($b in $bulges) {
        if ([Math]::Abs($b) -gt 1e-12) { return $true }
    }
    return $false
}

function Assert-NoBulges {
    <#
    .SYNOPSIS
      Throw if the polyline has any arc segments.
    #>
    param(
        [Parameter(Mandatory=$true)]$Polyline,
        [string]$Context = 'this operation'
    )
    if (Test-AnyBulge -Polyline $Polyline) {
        throw "Polyline handle '$($Polyline.Handle)' contains curved (bulge) segments. v1 of live-cad-edit does not support arcs; $Context refuses to operate on it. Handle curves manually in AutoCAD or wait for v2."
    }
}

function Set-PolylineVertex {
    <#
    .SYNOPSIS
      Move a single vertex on an LWPolyline by its 0-based index.
    .DESCRIPTION
      Reads .Coordinates (flat [x0,y0,x1,y1,...] double[]), mutates the two
      slots, assigns back. AutoCAD redraws live.
    .OUTPUTS
      Hashtable with OldX/OldY/NewX/NewY/Shift for logging.
    #>
    param(
        [Parameter(Mandatory=$true)]$Polyline,
        [Parameter(Mandatory=$true)][int]$Index,
        [Parameter(Mandatory=$true)][double]$NewX,
        [Parameter(Mandatory=$true)][double]$NewY
    )
    Invoke-WithComRetry {
        $coords = $Polyline.Coordinates
        $oldX = [double]$coords[2*$Index]
        $oldY = [double]$coords[2*$Index+1]
        $coords[2*$Index]   = $NewX
        $coords[2*$Index+1] = $NewY
        $Polyline.Coordinates = $coords
        return @{
            OldX = $oldX; OldY = $oldY
            NewX = $NewX; NewY = $NewY
            Shift = [Math]::Sqrt(($NewX-$oldX)*($NewX-$oldX) + ($NewY-$oldY)*($NewY-$oldY))
        }
    }
}
