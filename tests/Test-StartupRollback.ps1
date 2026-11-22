$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$fixture = Join-Path $projectRoot 'runtime\verification\startup-rollback'
New-Item -ItemType Directory -Path "$fixture\scripts", "$fixture\breeze\.venv\Scripts", "$fixture\parakeet\.venv\Scripts", "$fixture\breeze\model", "$fixture\parakeet\model" -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'Start-SpeechApi.ps1') -Destination "$fixture\Start-SpeechApi.ps1" -Force
foreach ($file in @('breeze\.venv\Scripts\python.exe', 'parakeet\.venv\Scripts\python.exe', 'breeze\model\model.safetensors.index.json', 'parakeet\model\model.safetensors')) {
    Set-Content -LiteralPath (Join-Path $fixture $file) -Value ''
}
$occupied = @(Get-NetTCPConnection -State Listen | Select-Object -ExpandProperty LocalPort)
$ports = @(50000..60000 | Where-Object { $_ -notin $occupied } | Select-Object -First 2)
@"
@{ RuntimeRoot = 'breeze'; ParakeetRoot = 'parakeet'; Port = $($ports[0]); WorkerPort = $($ports[1]) }
"@ | Set-Content -LiteralPath "$fixture\service.psd1"
@'
function Start-OwnedProcess($name, $python, $workingDirectory, $arguments, $port, $logs) {
    [pscustomobject]@{ Name = $name; ProcessId = 12345; Port = $port }
}
function Save-OwnedProcesses($records, $statePath) { throw 'Injected state-write failure' }
function Stop-OwnedProcess($record) { $global:rollbackNames.Add($record.Name) }
function Wait-Healthy($record, $timeoutSeconds, $logs) { }
'@ | Set-Content -LiteralPath "$fixture\scripts\Processes.ps1"
$global:rollbackNames = [System.Collections.Generic.List[string]]::new()
try {
    & "$fixture\Start-SpeechApi.ps1"
    throw 'Expected the injected startup failure.'
} catch {
    if ($_.Exception.Message -ne 'Injected state-write failure') { throw }
}
if ($global:rollbackNames.Count -ne 1 -or $global:rollbackNames[0] -ne 'breeze') {
    throw 'The newly started worker was not rolled back after state persistence failed.'
}
Remove-Variable -Name rollbackNames -Scope Global
Write-Output 'Startup rollback test passed; no real processes were launched.'
