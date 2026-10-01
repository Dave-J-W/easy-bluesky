<#
    Open a panel .ui in Qt Widgets Designer.

    Why this script exists rather than a bare path to designer.exe: the Designer in the
    conda env needs the env's Library\bin on PATH. Qt6Core.dll sits beside designer.exe,
    but ITS dependencies (ICU, pcre2, zstd, zlib) live in Library\bin, so launching the
    exe directly starts a process that never opens a window and prints nothing at all —
    MainWindowHandle stays 0 and the working set sits at ~5 MB instead of ~98 MB.

    Launching from Git Bash fails differently and more loudly:
        designer.exe: error while loading shared libraries: Qt6Core.dll

    Both were hit on 2026-10-01. Use this script.

    Usage:
        .\edit_panel.ps1                          # opens trough_panel.ui
        .\edit_panel.ps1 trough_panel_extended    # opens that one instead
        .\edit_panel.ps1 -Wait                    # block until Designer closes
#>
param(
    [string]$Panel = "trough_panel",
    [switch]$Wait
)

$ErrorActionPreference = "Stop"

$eb = Join-Path $env:USERPROFILE ".conda\eb"
$qt = Join-Path $eb "Library\lib\qt6"
$designer = Join-Path $qt "bin\designer.exe"

if (-not (Test-Path $designer)) {
    Write-Error "Designer not found at $designer. Create the env first - see README.md."
}

# Resolve the .ui next to this script, with or without the extension.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ui = Join-Path $here ($Panel -replace '\.ui$', '')
$ui = "$ui.ui"
if (-not (Test-Path $ui)) {
    $available = (Get-ChildItem $here -Filter *.ui | ForEach-Object { $_.BaseName }) -join ", "
    Write-Error "No such panel: $ui`nAvailable: $available"
}

# The activation that matters: Library\bin must precede everything.
$env:PATH = "$eb;$eb\Library\bin;$qt\bin;$env:PATH"
$env:QT_PLUGIN_PATH = "$qt\plugins"

Write-Host "Opening $(Split-Path -Leaf $ui) in Qt Widgets Designer..."
if ($Wait) {
    Start-Process -FilePath $designer -ArgumentList $ui -Wait
} else {
    $proc = Start-Process -FilePath $designer -ArgumentList $ui -PassThru
    Start-Sleep -Seconds 6
    $proc.Refresh()
    if ($proc.HasExited) {
        Write-Error "Designer exited immediately (code $($proc.ExitCode))."
    } elseif ($proc.MainWindowHandle -eq 0) {
        Write-Warning "Designer is running but has no window yet - if it does not appear, the Qt plugin path is wrong."
    } else {
        Write-Host "Running: pid $($proc.Id)  '$($proc.MainWindowTitle)'"
    }
}

Write-Host ""
Write-Host "When you have saved (Ctrl+S), check your edit:"
Write-Host "  `$env:QT_QPA_PLATFORM='offscreen'; & `"$eb\python.exe`" -m pytest `"$here`" -q"
Write-Host "  & `"$eb\python.exe`" `"$here\measure.py`"      # redraws the screenshots"
