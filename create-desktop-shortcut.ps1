$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
foreach ($s in @(
    @{ Name = "DMR Tracker"; Bat = "start-dmr-tracker.bat"; Desc = "Start DMR Tracker and open it in the browser" },
    @{ Name = "DMR Tracker (dev mode)"; Bat = "start-dmr-tracker-dev.bat"; Desc = "Start DMR Tracker in developer mode (live code reload)" }
)) {
    $lnk = $shell.CreateShortcut((Join-Path $desktop ($s.Name + ".lnk")))
    $lnk.TargetPath = Join-Path $root $s.Bat
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = (Join-Path $root "windows\dmr-tracker.ico") + ",0"
    $lnk.WindowStyle = 7
    $lnk.Description = $s.Desc
    $lnk.Save()
}
Write-Host "Shortcuts created on your Desktop: DMR Tracker, DMR Tracker (dev mode)"
