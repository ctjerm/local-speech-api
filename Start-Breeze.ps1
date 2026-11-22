[CmdletBinding()]
param([int]$TimeoutSeconds = 240)
& (Join-Path $PSScriptRoot 'Start-SpeechApi.ps1') -TimeoutSeconds $TimeoutSeconds
