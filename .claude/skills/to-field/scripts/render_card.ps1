# Render the field card HTML to PDF beside it. Writes to a temp file first, then copies, so a PDF that is
# open in a viewer fails loudly instead of leaving a stale card on disk.
# Usage: pwsh render_card.ps1 <card.html>
param([Parameter(Mandatory)][string]$Card)
$ErrorActionPreference = 'Stop'
$card = (Resolve-Path $Card).Path
$pdf = [IO.Path]::ChangeExtension($card, '.pdf')
$tmp = Join-Path $env:TEMP ("card_" + [guid]::NewGuid() + ".pdf")
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge not found" }
Start-Process -Wait $edge -ArgumentList '--headless=new', '--disable-gpu', '--no-pdf-header-footer', "--print-to-pdf=`"$tmp`"", "`"$card`""
if (-not (Test-Path $tmp)) { throw "Edge produced no PDF" }
try { Copy-Item $tmp $pdf -Force } catch { throw "Could not write $pdf (is it open in a PDF viewer? close it and re-run): $_" }
Remove-Item $tmp
Get-Item $pdf | Select-Object FullName, Length, LastWriteTime
