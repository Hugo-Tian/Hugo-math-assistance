param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$projectUrl = 'http://127.0.0.1:5173'
try {
    $health = Invoke-RestMethod "$projectUrl/api/health" -TimeoutSec 3
    $page = Invoke-WebRequest $projectUrl -UseBasicParsing -TimeoutSec 3
    if ($health.status -eq 'ok' -and $health.algorithm -eq 'rules-v1.0' -and $page.Content -match '/src/main.js') {
        Write-Host 'The project is already running.'
        if (!$NoBrowser) { Start-Process $projectUrl }
        exit 0
    }
} catch { }
$occupied = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 5173,8000
if ($occupied) {
    Write-Host 'Port 5173 or 8000 is occupied. Close the old project service or check the conflicting app.'
    $occupied | Select-Object LocalPort,OwningProcess | Format-Table
    exit 1
}
$browserJob = $null
if (!$NoBrowser) {
    $browserJob = Start-Job -ArgumentList $projectUrl -ScriptBlock {
        param($url)
        for ($attempt = 0; $attempt -lt 90; $attempt++) {
            try {
                $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
                if ($health.status -eq 'ok' -and $health.algorithm -eq 'rules-v1.0') {
                    Start-Process $url
                    return
                }
            } catch { }
            Start-Sleep -Seconds 1
        }
    }
}
try {
    Write-Host 'Starting Zhixu. Keep this window open; press Ctrl+C to stop.'
    & "$PSScriptRoot/start.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    if ($browserJob) { Stop-Job $browserJob; Remove-Job $browserJob }
}
