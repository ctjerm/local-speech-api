[CmdletBinding()]
param([Parameter(Mandatory)][string]$Address)
$ErrorActionPreference = 'Stop'
$tls = Join-Path $PSScriptRoot 'runtime\tls'
New-Item -ItemType Directory -Path $tls -Force | Out-Null
# Private keys stay in the project, readable only by this account and SYSTEM.
$acl = Get-Acl -LiteralPath $tls
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @([System.Security.Principal.WindowsIdentity]::GetCurrent().User, [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
}
Set-Acl -LiteralPath $tls -AclObject $acl
$sha = [System.Security.Cryptography.HashAlgorithmName]::SHA256
$padding = [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
$rootKey = [System.Security.Cryptography.RSA]::Create(3072)
$serverKey = [System.Security.Cryptography.RSA]::Create(2048)
try {
    $caPath = Join-Path $tls 'local-ca.cer'
    $caKeyPath = Join-Path $tls 'local-ca-key.pem'
    if (Test-Path -LiteralPath $caPath) {
        $rootKey.ImportFromPem([System.IO.File]::ReadAllText($caKeyPath))
        $publicRoot = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($caPath)
        $root = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::CopyWithPrivateKey($publicRoot, $rootKey)
    } else {
        $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=Voice room Local CA', $rootKey, $sha, $padding)
        $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true, $true, 0, $true))
        $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new('KeyCertSign,CrlSign', $true))
        $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509SubjectKeyIdentifierExtension]::new($request.PublicKey, $false))
        $root = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddYears(5))
        [System.IO.File]::WriteAllBytes($caPath, $root.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
        [System.IO.File]::WriteAllText($caKeyPath, $rootKey.ExportPkcs8PrivateKeyPem())
        [System.IO.File]::WriteAllText((Join-Path $tls 'local-ca.pem'), $root.ExportCertificatePem())
    }
    $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new("CN=$Address", $serverKey, $sha, $padding)
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true))
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new('DigitalSignature,KeyEncipherment', $true))
    $uses = [System.Security.Cryptography.OidCollection]::new()
    $uses.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1')) | Out-Null
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($uses, $false))
    $san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $san.AddIpAddress([System.Net.IPAddress]::Parse($Address))
    $san.AddIpAddress([System.Net.IPAddress]::Loopback)
    $san.AddDnsName('localhost')
    $san.AddDnsName([Environment]::MachineName)
    $request.CertificateExtensions.Add($san.Build())
    $serial = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(16)
    $certificate = $request.Create($root, [DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(365), $serial)
    [System.IO.File]::WriteAllText((Join-Path $tls 'server.pem'), $certificate.ExportCertificatePem())
    [System.IO.File]::WriteAllText((Join-Path $tls 'server-key.pem'), $serverKey.ExportPkcs8PrivateKeyPem())
    Write-Output "HTTPS certificate prepared for $Address and localhost. Restart the service to enable port 8443."
    Write-Output "Public certificate to trust on clients: $caPath"
    Write-Output "CA SHA-256: $($root.GetCertHashString($sha))"
    Write-Output 'No certificate was added to any trusted store.'
} finally {
    $rootKey.Dispose()
    $serverKey.Dispose()
    if ($root) { $root.Dispose() }
    if ($certificate) { $certificate.Dispose() }
    if ($publicRoot) { $publicRoot.Dispose() }
}
