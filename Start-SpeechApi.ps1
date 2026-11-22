[CmdletBinding()]
param([int]$TimeoutSeconds = 240)
$ErrorActionPreference = 'Stop'
$config = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'service.psd1')
$config.RuntimeRoot = Join-Path $PSScriptRoot $config.RuntimeRoot
$config.ParakeetRoot = Join-Path $PSScriptRoot $config.ParakeetRoot
. (Join-Path $PSScriptRoot 'scripts\Processes.ps1')
$statePath = Join-Path $PSScriptRoot 'runtime\service.json'
$logs = Join-Path $PSScriptRoot 'runtime\logs'
$breezePython = Join-Path $config.RuntimeRoot '.venv\Scripts\python.exe'
$apiPython = Join-Path $config.ParakeetRoot '.venv\Scripts\python.exe'
$tls = Join-Path $PSScriptRoot 'runtime\tls'
$httpsEnabled = Test-Path -LiteralPath "$tls\server.pem"
$ports = @($config.Port, $config.WorkerPort)
if ($httpsEnabled) { $ports += $config.HttpsPort }
foreach ($file in @($breezePython, $apiPython, "$($config.RuntimeRoot)\model\model.safetensors.index.json", "$($config.ParakeetRoot)\model\model.safetensors")) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing $file. Run Install-SpeechApi.ps1 first." }
}
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $alive = @($state.Processes | Where-Object {
        $process = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        $process -and $process.StartTime.ToUniversalTime().Ticks -eq [long]$_.StartTimeUtcTicks -and $process.Path -eq $_.Python
    })
    if ($alive.Count -eq 2 -and (-not $httpsEnabled -or $alive[1].HttpsPort -eq $config.HttpsPort)) {
        Wait-Healthy $alive[1] 5 $logs
        Write-Output "Speech API is already running: http://localhost:$($config.Port)/docs"
        return
    }
    & (Join-Path $PSScriptRoot 'Stop-SpeechApi.ps1')
}
foreach ($port in $ports) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is occupied. No process was stopped." }
}
New-Item -ItemType Directory -Path $logs, "$PSScriptRoot\runtime\temp", "$PSScriptRoot\runtime\cache" -Force | Out-Null
$env:TEMP = "$PSScriptRoot\runtime\temp"
$env:TMP = $env:TEMP
$env:HF_HOME = "$PSScriptRoot\runtime\cache\huggingface"
$env:TORCH_HOME = "$PSScriptRoot\runtime\cache\torch"
$env:NUMBA_CACHE_DIR = "$PSScriptRoot\runtime\cache\numba"
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
$env:PYTHONDONTWRITEBYTECODE = '1'
$records = [System.Collections.Generic.List[object]]::new()
try {
    $worker = Start-OwnedProcess 'breeze' $breezePython "$($config.RuntimeRoot)\upstream" @('-u', '-m', 'breeze_infer.api', "`"$($config.RuntimeRoot)\model`"", '--host', '127.0.0.1', '--port', $config.WorkerPort, '--no-fast-all') $config.WorkerPort $logs
    $records.Add($worker)
    Save-OwnedProcesses $records $statePath
    Wait-Healthy $worker $TimeoutSeconds $logs
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    $arguments = @('-u', '-m', 'speech_api', '--model', "`"$($config.ParakeetRoot)\model`"", '--worker-port', $config.WorkerPort, '--port', $config.Port)
    if ($httpsEnabled) {
        $arguments += @('--https-port', $config.HttpsPort, '--certificate', "`"$tls\server.pem`"", '--key', "`"$tls\server-key.pem`"", '--ca-certificate', "`"$tls\local-ca.cer`"")
    }
    $api = Start-OwnedProcess 'api' $apiPython $PSScriptRoot $arguments $config.Port $logs
    if ($httpsEnabled) { $api | Add-Member -NotePropertyName HttpsPort -NotePropertyValue $config.HttpsPort }
    $records.Add($api)
    Save-OwnedProcesses $records $statePath
    Wait-Healthy $api $TimeoutSeconds $logs
    if ($httpsEnabled) {
        & $apiPython -c "import ssl,sys,urllib.request; urllib.request.urlopen('https://localhost:'+sys.argv[1]+'/health',context=ssl.create_default_context(cafile=sys.argv[2]),timeout=10).read()" $config.HttpsPort "$tls\local-ca.pem"
        if ($LASTEXITCODE -ne 0) { throw 'HTTPS health verification failed.' }
    }
} catch {
    $startupError = $_
    # State persistence itself can fail. Roll back the processes we actually
    # started, using memory rather than trusting a possibly incomplete file.
    $rollback = $records.ToArray()
    [array]::Reverse($rollback)
    $cleanupFailed = $false
    foreach ($record in $rollback) {
        try { Stop-OwnedProcess $record }
        catch { $cleanupFailed = $true; Write-Warning "Cleanup failed for $($record.Name), PID $($record.ProcessId): $_" }
    }
    if (-not $cleanupFailed) {
        foreach ($file in @($statePath, "$statePath.tmp")) {
            if (Test-Path -LiteralPath $file) {
                try { Remove-Item -LiteralPath $file }
                catch { Write-Warning "Could not remove process state $file : $_" }
            }
        }
    }
    throw $startupError
}
Write-Output "Speech API ready: http://localhost:$($config.Port)/docs"
if ($httpsEnabled) { Write-Output "HTTPS website: https://localhost:$($config.HttpsPort)/" }
Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | ForEach-Object {
    Write-Output "LAN: http://$($_.IPv4Address.IPAddress):$($config.Port)/docs"
    if ($httpsEnabled) { Write-Output "LAN microphone: https://$($_.IPv4Address.IPAddress):$($config.HttpsPort)/" }
}
