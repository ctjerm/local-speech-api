[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\Processes.ps1')
$statePath = Join-Path $PSScriptRoot 'runtime\service.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No tracked speech API processes.'; return }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$records = @($state.Processes)
[array]::Reverse($records)
foreach ($record in $records) { Stop-OwnedProcess $record }
Remove-Item -LiteralPath $statePath
Write-Output 'Speech API stopped; its listening ports are released.'
