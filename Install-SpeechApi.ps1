[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'scripts\Install-Breeze.ps1')
& (Join-Path $PSScriptRoot 'scripts\Install-Parakeet.ps1')
Write-Output 'Both models are installed. Run Start-SpeechApi.ps1.'
