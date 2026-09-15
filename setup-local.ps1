# پروزه اتوماسیون بورسی
param([string]$Python = 'python', [switch]$InstallDocumentTools)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $Python -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12 on both devices"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required for this setup.' }
if (!(Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$localConfig = Join-Path $projectRoot 'config.local.toml'
if (!(Test-Path -LiteralPath $localConfig)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config.example.toml') -Destination $localConfig
}
if ($InstallDocumentTools) {
    & $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-docs.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Document dependency installation failed.' }
}
& $venvPython (Join-Path $projectRoot 'check-local.py')
if ($LASTEXITCODE -ne 0) { throw 'Local readiness check failed.' }
Write-Output 'Local setup prepared. The application server is not implemented yet.'

