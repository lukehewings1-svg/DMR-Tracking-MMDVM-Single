$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop "DMR Tracker.lnk"))
$lnk.TargetPath = Join-Path $root "start-dmr-tracker.bat"
$lnk.WorkingDirectory = $root
$lnk.IconLocation = (Join-Path $root "windows\dmr-tracker.ico") + ",0"
$lnk.WindowStyle = 7
$lnk.Description = "Start DMR Tracker and open it in the browser"
$lnk.Save()
Write-Host "Shortcut created on your Desktop: DMR Tracker"
