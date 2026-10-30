param([switch]$Install)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create virtual environment. Use Python 3.11+.' }
    $Install = $true
}
if ($Install) {
    & ./.venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
}
& ./.venv/Scripts/python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
& ./.venv/Scripts/python.exe -m backend.seed
if ($LASTEXITCODE -ne 0) { throw 'Database seed failed' }
& ./.venv/Scripts/python.exe scripts/init_knowledge.py
if ($LASTEXITCODE -ne 0) { throw 'Knowledge seed failed' }
$projectPython = Join-Path (Get-Location) '.venv/Scripts/python.exe'
$projectBackend = Start-Process -FilePath $projectPython -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WindowStyle Hidden -PassThru
try {
    Write-Host 'Open http://127.0.0.1:5173 . Press Ctrl+C here to stop this launcher.'
    npm run dev
    if ($LASTEXITCODE -ne 0) { throw 'Frontend startup failed' }
} finally {
    if (!$projectBackend.HasExited) { Stop-Process -Id $projectBackend.Id }
}
