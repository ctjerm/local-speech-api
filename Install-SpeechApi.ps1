[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Install-Breeze.ps1')
& (Join-Path $PSScriptRoot 'Install-Parakeet.ps1')
Write-Output 'Both models are installed. Run Start-SpeechApi.ps1.'
