# Sends this computer's webcam to the CrowdFlow gateway (Windows PowerShell). Needs ffmpeg and the repo's .env.
# Usage:  .\scripts\webcam\start-webcam.ps1                       (first camera found)
#         .\scripts\webcam\start-webcam.ps1 -Device "Integrated Camera"
# Stop with Ctrl+C. -TestPattern sends a test picture instead of the webcam.
param([string]$Device = "", [switch]$TestPattern, [string]$Url = "")
$root = Join-Path $PSScriptRoot "..\.."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "ffmpeg not found. Install it with:  winget install Gyan.FFmpeg   then close and reopen PowerShell."; exit 1
}
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { Write-Host "No .env found. Run .\scripts\make-env.ps1 first."; exit 1 }
$vars = @{}; Get-Content $envFile | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { $vars[$Matches[1].Trim()] = $Matches[2].Trim() } }
if (-not $Url) { $Url = "rtsp://$($vars['GATEWAY_PUBLISH_USER']):$($vars['GATEWAY_PUBLISH_PASSWORD'])@127.0.0.1:8554/webcam" }
$out = @("-c:v","libx264","-preset","ultrafast","-tune","zerolatency","-g","15","-pix_fmt","yuv420p","-f","rtsp","-rtsp_transport","tcp",$Url)
if ($TestPattern) { & ffmpeg -re -f lavfi -i "testsrc=size=640x480:rate=15" @out; exit }
if (-not $Device) {
  $list = & cmd /c "ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1"
  $m = $list | Select-String -Pattern '"([^"]+)" \(video\)' | Select-Object -First 1
  if (-not $m) { Write-Host "No camera found. Check a webcam is connected and Windows Settings > Privacy > Camera allows desktop apps."; $list; exit 1 }
  $Device = $m.Matches[0].Groups[1].Value
}
Write-Host "Using camera: $Device"
& ffmpeg -f dshow -framerate 15 -video_size 640x480 -i "video=$Device" @out
