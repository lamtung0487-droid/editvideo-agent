$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Không tạo được Python virtual environment' }
    $taskRequirements = if (Test-Path -LiteralPath 'requirements.lock.txt') { 'requirements.lock.txt' } else { 'requirements.txt' }
    & $taskPython -m pip install -r $taskRequirements
    if ($LASTEXITCODE -ne 0) { throw 'Không cài được thư viện' }
}
if (-not (Test-Path -LiteralPath 'engines\node_modules')) {
    Push-Location engines
    try {
        npm ci --no-audit --no-fund 1>&2
        if ($LASTEXITCODE -ne 0) { throw 'Không cài được engine video' }
    } finally { Pop-Location }
}
# stdout belongs to the MCP protocol. No banner or startup logging here.
& $taskPython run.py @args
