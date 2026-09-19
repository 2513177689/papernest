$ErrorActionPreference = 'Stop'
$expectedPython = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.venv/Scripts/python.exe'))
$listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    $parentCandidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($candidate.ParentProcessId)"
    $owned = ($candidate.ExecutablePath -eq $expectedPython) -or ($parentCandidate.ExecutablePath -eq $expectedPython)
    if ($owned -and $candidate.CommandLine -match 'run.py') {
        Stop-Process -Id $candidate.ProcessId
        Write-Host 'PaperNest stopped.'
    }
}
