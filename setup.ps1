param([switch]$Vision,[switch]$Temporal,[switch]$Voice)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# a slow mirror is retried instead of failing the install (a clean-clone test timed out on numpy)
if (-not $env:PIP_DEFAULT_TIMEOUT) { $env:PIP_DEFAULT_TIMEOUT = '60' }
if (-not $env:PIP_RETRIES) { $env:PIP_RETRIES = '5' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required (python --version)' }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment' }
}
& $taskPython -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot install Python dependencies' }
Push-Location engines
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install video engines' }
    # Remotion's headless Chrome (~120 MB), once: otherwise the first renders each start the download and can time out
    node --input-type=module -e "const r = await import('@remotion/renderer'); await r.ensureBrowser(); console.log('Remotion browser ready')"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download the Remotion browser' }
} finally { Pop-Location }
if ($Vision -or $Temporal) {
    & $taskPython -m pip install -r requirements.vision.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install vision runtime' }
    $taskOldCuda = $env:SAM2_BUILD_CUDA
    try {
        $env:SAM2_BUILD_CUDA = '0'
        & $taskPython -m pip install --no-build-isolation --no-deps 'git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot install pinned SAM2 backend' }
        & $taskPython scripts/setup_vision.py
        if ($LASTEXITCODE -ne 0) { throw 'Cannot download vision models' }
    } finally { $env:SAM2_BUILD_CUDA = $taskOldCuda }
}
if ($Temporal) {
    & $taskPython -m pip install -r requirements.temporal.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install temporal runtime' }
    & $taskPython scripts/setup_temporal.py --backend all
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install temporal inpainting and local footage models' }
}
if ($Voice) {
    # Offline Vietnamese narration: Piper (GPL-3.0, separate process) + vi_VN vais1000 voice (~97 MB in total).
    & $taskPython -m pip install -r requirements.voice.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install Piper' }
    & $taskPython scripts/setup_voice.py --whisper
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download the Piper voice' }
}
$taskMcp = Join-Path $PSScriptRoot '.mcp.json'

if (-not (Test-Path -LiteralPath $taskMcp)) {
    # Client configuration for this clone (absolute paths of this machine; .mcp.example.json is the template).
    $taskConfig = @{ mcpServers = @{ editvideo = @{ type = 'stdio'; command = $taskPython; args = @((Join-Path $PSScriptRoot 'run.py')); env = @{ PYTHONIOENCODING = 'utf-8' } } } }
    $taskConfig | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskMcp -Encoding utf8
}
Write-Host 'EditVideo Agent ready. Configure your AI client with .mcp.json.'
