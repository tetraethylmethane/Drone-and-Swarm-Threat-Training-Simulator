<#
.SYNOPSIS
  Manage an isolated, project-local PostgreSQL cluster for development and tests.

.DESCRIPTION
  Uses the PostgreSQL binaries already installed on the workstation to run a
  *separate* cluster on its own port. It never touches the system cluster.
  Data lives under %LOCALAPPDATA%\drikr\pgdata (outside OneDrive, whose file
  locking is unsafe for database files).

  This is the deliberately scoped local development mode described in
  docs/architecture/architecture-decisions.md (ADR-004). Production-style
  deployment uses the PostgreSQL container in docker-compose.yml.

.EXAMPLE
  ./scripts/local-postgres.ps1 init
  ./scripts/local-postgres.ps1 start
  ./scripts/local-postgres.ps1 status
  ./scripts/local-postgres.ps1 stop
#>
param(
  [Parameter(Mandatory = $true)][ValidateSet('init', 'start', 'stop', 'status')][string]$Action,
  [int]$Port = 55432,
  [string]$PgBin = $env:DRIKR_PG_BIN
)

$ErrorActionPreference = 'Stop'
if (-not $PgBin) {
  $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
    Sort-Object { [int]($_.Name -replace '\D', '') } -Descending | Select-Object -First 1
  if (-not $candidate) { throw 'PostgreSQL binaries not found. Set DRIKR_PG_BIN to the bin directory.' }
  $PgBin = Join-Path $candidate.FullName 'bin'
}
$root = Join-Path $env:LOCALAPPDATA 'drikr'
$data = Join-Path $root 'pgdata'
$log = Join-Path $root 'postgres.log'

switch ($Action) {
  'init' {
    if (Test-Path (Join-Path $data 'PG_VERSION')) { Write-Output "Cluster already initialised at $data"; break }
    New-Item -ItemType Directory -Force $root | Out-Null
    $pwFile = Join-Path $root 'pwfile.tmp'
    # Development-only superuser password; matches .env.example. Never reuse in production.
    Set-Content -Path $pwFile -Value 'drikr_dev_only' -Encoding ascii -NoNewline
    & (Join-Path $PgBin 'initdb.exe') -D $data -U drikr --pwfile=$pwFile --auth=scram-sha-256 --encoding=UTF8 --locale=C | Out-Null
    Remove-Item $pwFile -Force
    # Listen on loopback only.
    Add-Content -Path (Join-Path $data 'postgresql.conf') -Value "`nlisten_addresses = '127.0.0.1'`nport = $Port`n"
    Write-Output "Initialised cluster at $data (port $Port, user drikr)"
  }
  'start' {
    # Start-Process prevents the postmaster from inheriting this console's pipes,
    # which would otherwise keep the calling shell attached indefinitely.
    & (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p $Port | Out-Null
    if ($LASTEXITCODE -ne 0) {
      # No -Wait: in Windows PowerShell 5.1 it also waits for descendant processes (the postmaster).
      Start-Process -FilePath (Join-Path $PgBin 'pg_ctl.exe') -ArgumentList @('-D', "`"$data`"", '-l', "`"$log`"", 'start') -WindowStyle Hidden
      for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        & (Join-Path $PgBin 'pg_isready.exe') -h 127.0.0.1 -p $Port | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
      }
      if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become ready; see $log" }
    }
    $env:PGPASSWORD = 'drikr_dev_only'
    foreach ($db in 'drikr', 'drikr_test') {
      $exists = & (Join-Path $PgBin 'psql.exe') -h 127.0.0.1 -p $Port -U drikr -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'"
      if (-not $exists) { & (Join-Path $PgBin 'createdb.exe') -h 127.0.0.1 -p $Port -U drikr $db }
    }
    Write-Output "PostgreSQL running on 127.0.0.1:$Port (databases: drikr, drikr_test)"
  }
  'stop' { & (Join-Path $PgBin 'pg_ctl.exe') -D $data -m fast -w stop }
  'status' { & (Join-Path $PgBin 'pg_ctl.exe') -D $data status }
}
