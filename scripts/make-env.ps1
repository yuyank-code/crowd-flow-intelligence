# Creates .env with fresh secrets for camera/laptop mode (Windows PowerShell).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .env) { Write-Host ".env already exists - leaving it alone."; exit 0 }
function Get-Bytes($n) { $b = New-Object byte[] $n; (New-Object System.Security.Cryptography.RNGCryptoServiceProvider).GetBytes($b); ,$b }
function Hex($n) { -join ((Get-Bytes $n) | ForEach-Object { $_.ToString("x2") }) }
$fernet = [Convert]::ToBase64String((Get-Bytes 32)).Replace("+", "-").Replace("/", "_")
$key = Hex 24
@(
  "OPERATOR_API_KEY=$key",
  "CCTV_SECRET_KEY=$fernet",
  "PLAYBACK_SIGNING_KEY=$(Hex 24)",
  "MEDIA_GATEWAY_BASE_URL=http://mediamtx-laptop:8888",
  "MEDIA_GATEWAY_PUBLIC_URL=http://localhost:8888",
  "GATEWAY_PUBLISH_USER=webcam",
  "GATEWAY_PUBLISH_PASSWORD=$(Hex 24)"
) | Set-Content -Encoding ASCII .env
Write-Host "Created .env. Your operator key (type it into the Cameras tab):"
Write-Host $key
