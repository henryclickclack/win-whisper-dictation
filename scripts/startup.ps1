param(
    [ValidateSet("Install", "Remove")]
    [string]$Action = "Install",
    [string]$Executable = ""
)

$ErrorActionPreference = "Stop"
$startupDirectory = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDirectory "Whisper Shortcut.lnk"

if ($Action -eq "Remove") {
    Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
    Write-Host "Removed Whisper Shortcut from Windows startup."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Executable)) {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $Executable = Join-Path $projectRoot "dist\WhisperShortcut\WhisperShortcut.exe"
}

$Executable = [IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Executable not found: $Executable. Build it first or pass -Executable."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $Executable
$shortcut.WorkingDirectory = Split-Path -Parent $Executable
$shortcut.Description = "Local voice dictation hotkey"
$shortcut.Save()

Write-Host "Whisper Shortcut will now start when you sign in."
