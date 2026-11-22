function Save-OwnedProcesses($records, $statePath) {
    $temporaryPath = "$statePath.tmp"
    @{ Processes = @($records.ToArray()) } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force
}

function Stop-OwnedProcess($record) {
    $process = Get-Process -Id $record.ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        if ($process.StartTime.ToUniversalTime().Ticks -ne [long]$record.StartTimeUtcTicks -or $process.Path -ne $record.Python) {
            throw "PID $($record.ProcessId) no longer belongs to $($record.Name). Nothing was stopped."
        }
        & taskkill.exe /PID $record.ProcessId /T /F
        if ($LASTEXITCODE -ne 0) { throw "Could not stop $($record.Name)." }
        $process.WaitForExit(10000) | Out-Null
    }
    $deadline = (Get-Date).AddSeconds(10)
    $ports = @($record.Port)
    if ($record.HttpsPort) { $ports += $record.HttpsPort }
    while (Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $deadline) { throw "A listening port for $($record.Name) is still occupied. Inspect it before restarting." }
        Start-Sleep -Milliseconds 200
    }
}

function Start-OwnedProcess($name, $python, $workingDirectory, $arguments, $port, $logs) {
    $process = Start-Process -FilePath $python -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru `
        -ArgumentList $arguments -RedirectStandardOutput "$logs\$name.stdout.log" -RedirectStandardError "$logs\$name.stderr.log"
    return [pscustomobject]@{
        Name = $name
        ProcessId = $process.Id
        StartTimeUtcTicks = $process.StartTime.ToUniversalTime().Ticks.ToString()
        Python = $python
        Port = $port
    }
}

function Wait-Healthy($record, $timeoutSeconds, $logs) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $process = Get-Process -Id $record.ProcessId -ErrorAction SilentlyContinue
        if (-not $process -or $process.StartTime.ToUniversalTime().Ticks -ne [long]$record.StartTimeUtcTicks) {
            Get-Content -LiteralPath "$logs\$($record.Name).stderr.log" -Tail 25 | Write-Host
            throw "$($record.Name) exited during startup. See $logs."
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($record.Port)/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw "$($record.Name) did not become ready within $timeoutSeconds seconds."
}
