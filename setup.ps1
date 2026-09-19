$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
$pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
$bundledPnpm = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pnpm/bin/pnpm.cjs'
$npmCommand = Get-Command npm -ErrorAction SilentlyContinue
Push-Location frontend
try {
    if ($pnpmCommand) {
        & $pnpmCommand.Source install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' }
        & $pnpmCommand.Source run build
    } elseif (Test-Path -LiteralPath $bundledPnpm) {
        node $bundledPnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' }
        node $bundledPnpm run build
    } elseif ($npmCommand) {
        & $npmCommand.Source install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed.' }
        & $npmCommand.Source run build
    } else { throw 'Install Node.js and npm or pnpm, then rerun setup.ps1.' }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Ready. Run start.ps1 to launch PaperNest.'
