#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$config = Import-PowerShellDataFile (Join-Path (Split-Path $PSScriptRoot -Parent) 'service.psd1')
$ruleName = 'LocalSpeechAPI-PrivateLAN'
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    throw "Rule $ruleName already exists. Inspect its scope before changing it."
}
New-NetFirewallRule -Name $ruleName -DisplayName 'Local Speech API - Private LAN' `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort $config.Port,$config.HttpsPort `
    -Profile Private -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block | Out-Null
Get-NetFirewallRule -Name $ruleName | Select-Object DisplayName, Enabled, Profile, Direction, Action
Write-Output "TCP $($config.Port) and $($config.HttpsPort) are allowed from the local subnet on Private networks."
