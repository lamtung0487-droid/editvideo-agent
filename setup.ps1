param([switch]$Vision,[switch]$Temporal,[switch]$Voice)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Native([string]$Failure, [scriptblock]$Step) {
    # Windows PowerShell 5.1 under 'Stop' turns a tool's first stderr line (pip's [notice], npm's warnings) into a
    # terminating error once the output is redirected (2>&1, *>, Tee-Object, an AI agent's shell): tools are judged by
    # their exit code instead, and their stderr is shown as plain lines.
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = -1  # stays -1 when the tool never started
    & $Step 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

foreach ($tool in 'python', 'node', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not on PATH: install it (INSTALL.md, section 2) and reopen PowerShell" }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning 'ffmpeg is not on PATH: setup continues, but renders and tests need it (INSTALL.md, section 2)' }
# Installed files reach ~155 characters below this folder (a package in .venv, Remotion's Chrome). Windows refuses paths
# over 260 characters unless long paths are enabled, and pip or npm then fail halfway with a misleading error.
$taskLongPaths = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -ErrorAction SilentlyContinue).LongPathsEnabled
if ($PSScriptRoot.Length -gt 100 -and $taskLongPaths -ne 1) {
    throw "This folder's path is $($PSScriptRoot.Length) characters long and installed files reach ~155 characters below it, past Windows' 260-character limit. Clone into a shorter path (for example C:\src\editvideo-agent) or enable long paths (INSTALL.md, Troubleshooting)."
}
# a slow mirror is retried instead of failing the install (a clean-clone test timed out on numpy)
if (-not $env:PIP_DEFAULT_TIMEOUT) { $env:PIP_DEFAULT_TIMEOUT = '60' }
if (-not $env:PIP_RETRIES) { $env:PIP_RETRIES = '5' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Invoke-Native 'Python 3.11 or newer is required (python --version)' { python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" }
    Invoke-Native 'Cannot create Python environment' { python -m venv .venv }
}
Invoke-Native 'Cannot install Python dependencies' { & $taskPython -m pip install -r requirements.lock.txt }
Push-Location engines
try {
    Invoke-Native 'Cannot install video engines' { npm ci --no-audit --no-fund }
    # Remotion's headless Chrome (~120 MB), once: otherwise the first renders each start the download and can time out
    Invoke-Native 'Cannot download the Remotion browser' { node --input-type=module -e "const r = await import('@remotion/renderer'); await r.ensureBrowser(); console.log('Remotion browser ready')" }
} finally { Pop-Location }
if ($Vision -or $Temporal) {
    Invoke-Native 'Cannot install vision runtime' { & $taskPython -m pip install -r requirements.vision.txt }
    $taskOldCuda = $env:SAM2_BUILD_CUDA
    try {
        $env:SAM2_BUILD_CUDA = '0'
        Invoke-Native 'Cannot install pinned SAM2 backend' { & $taskPython -m pip install --no-build-isolation --no-deps 'git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4' }
        Invoke-Native 'Cannot download vision models' { & $taskPython scripts/setup_vision.py }
    } finally { $env:SAM2_BUILD_CUDA = $taskOldCuda }
}
if ($Temporal) {
    Invoke-Native 'Cannot install temporal runtime' { & $taskPython -m pip install -r requirements.temporal.txt }
    Invoke-Native 'Cannot install temporal inpainting and local footage models' { & $taskPython scripts/setup_temporal.py --backend all }
}
if ($Voice) {
    # Offline Vietnamese narration: Piper (GPL-3.0, separate process) + vi_VN vais1000 voice (~97 MB in total).
    Invoke-Native 'Cannot install Piper' { & $taskPython -m pip install -r requirements.voice.txt }
    Invoke-Native 'Cannot download the Piper voice' { & $taskPython scripts/setup_voice.py --whisper }
}
$taskMcp = Join-Path $PSScriptRoot '.mcp.json'

if (-not (Test-Path -LiteralPath $taskMcp)) {
    # Client configuration for this clone (absolute paths of this machine; .mcp.example.json is the template).
    $taskConfig = @{ mcpServers = @{ editvideo = @{ type = 'stdio'; command = $taskPython; args = @((Join-Path $PSScriptRoot 'run.py')); env = @{ PYTHONIOENCODING = 'utf-8' } } } }
    # without a byte-order mark: Set-Content -Encoding utf8 writes one on Windows PowerShell 5.1, and JSON readers refuse it
    [System.IO.File]::WriteAllText($taskMcp, ($taskConfig | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $false))
}
Write-Host 'EditVideo Agent ready. Configure your AI client with .mcp.json.'
