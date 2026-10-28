$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
# Installing here wrote pip's output to stdout, which belongs to the MCP protocol: setup.ps1 installs, this only starts.
if (-not (Test-Path -LiteralPath $taskPython) -or -not (Test-Path -LiteralPath 'engines\node_modules')) {
    throw 'EditVideo Agent is not installed in this folder: run ./setup.ps1 first (INSTALL.md)'
}
# stdout belongs to the MCP protocol. No banner or startup logging here.
& $taskPython run.py @args
exit $LASTEXITCODE
