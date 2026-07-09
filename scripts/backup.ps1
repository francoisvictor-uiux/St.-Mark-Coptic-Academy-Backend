# Nightly backup: PostgreSQL dump + media files (spec Part 4 §5.10).
# Usage:  powershell -File scripts\backup.ps1 [-BackupDir D:\backups\stmark] [-KeepDays 14]
# Schedule with Task Scheduler (daily) or cron on Linux (see docs/deployment.md).
param(
    [string]$BackupDir = "D:\backups\stmark",
    [int]$KeepDays = 14
)

$ErrorActionPreference = "Stop"
$backendDir = Split-Path -Parent $PSScriptRoot

# DATABASE_URL from .env → pg_dump arguments
$envLine = Get-Content (Join-Path $backendDir ".env") | Where-Object { $_ -match "^DATABASE_URL=" }
if (-not $envLine) { throw "DATABASE_URL not found in backend/.env" }
$url = $envLine -replace "^DATABASE_URL=", ""
if ($url -notmatch "^postgres://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)$") { throw "Unrecognized DATABASE_URL format" }
$dbUser = $Matches[1]; $dbPass = $Matches[2]; $dbHost = $Matches[3]; $dbPort = $Matches[4]; $dbName = $Matches[5]

$pgDump = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
if (-not (Test-Path $pgDump)) { $pgDump = "pg_dump" }  # PATH fallback (Linux)

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"

# 1) Database (custom format — restore with pg_restore)
$dbFile = Join-Path $BackupDir "stmark_$stamp.dump"
$env:PGPASSWORD = $dbPass
& $pgDump -U $dbUser -h $dbHost -p $dbPort -F c -f $dbFile $dbName
Remove-Item Env:\PGPASSWORD
Write-Host "db backup: $dbFile ($([math]::Round((Get-Item $dbFile).Length/1KB)) KB)"

# 2) Media (uploaded images/documents)
$mediaSrc = Join-Path $backendDir "media"
if (Test-Path $mediaSrc) {
    $mediaFile = Join-Path $BackupDir "media_$stamp.zip"
    Compress-Archive -Path "$mediaSrc\*" -DestinationPath $mediaFile -Force
    Write-Host "media backup: $mediaFile"
}

# 3) Retention
Get-ChildItem $BackupDir | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Force
Write-Host "retention: kept last $KeepDays days"

# Restore reference:
#   pg_restore -U <user> -h <host> -d <fresh-db> --clean --if-exists stmark_<stamp>.dump
#   Expand-Archive media_<stamp>.zip -DestinationPath backend/media
