# Local HTTPS and microphone access

Browsers expose microphone capture only in a secure context: a trusted HTTPS origin or localhost. The HTTP LAN IP address does not qualify. See [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) and [W3C secure contexts](https://www.w3.org/TR/secure-contexts/).

FastAPI now runs through Hypercorn 0.18.0. Its documented `bind` and `insecure_bind` options serve HTTPS on 8443 and HTTP on 7860 using the same application and model instance. Existing API clients keep their HTTP endpoint. The private Breeze worker still uses Uvicorn on loopback 7861. References: [Hypercorn configuration](https://hypercorn.readthedocs.io/en/latest/how_to_guides/configuring.html), [programmatic serving](https://hypercorn.readthedocs.io/en/latest/how_to_guides/api_usage.html).

## Certificate files and trust

`Setup-Https.ps1` uses .NET's X.509 APIs to create a local certificate authority and a server certificate for the supplied LAN IP, localhost, loopback and the computer name. All files live in `runtime/tls`. Directory permissions are limited to the current Windows user and SYSTEM. `local-ca-key.pem` and `server-key.pem` are private and must stay there; runtime is excluded from Git. Only the public `local-ca.cer` is downloadable through `/setup/local-ca.cer`.

The CA, **Voice room Local CA**, is valid for five years and the server certificate for one. Setup prints the CA's SHA-256 fingerprint and adds it to no trust store. Each device that records over HTTPS needs the public CA installed once. The setup page at `http://<server-ip>:7860/assets/recording/setup.html` offers the download, the fingerprint and platform instructions. For iOS/iPadOS, installing the profile must be followed by enabling full trust in Certificate Trust Settings ([Apple instructions](https://support.apple.com/en-us/102390)). Android settings vary; use the CA certificate installation option, not a Wi-Fi client certificate. Windows uses the Current User trusted root store ([Microsoft documentation](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate)).

Trusting a local CA authorizes certificates signed by its private key. Keep the keys private and distribute only the public certificate. To remove trust on Windows after retiring the service, remove the named certificate from Trusted Root Certification Authorities in `certmgr.msc`. Remove its profile/certificate on other devices too.

## Start, renew and change IP

Start detects `runtime/tls/server.pem` and enables both listeners. HTTPS readiness is checked using the public CA file, without bypassing certificate validation. Stop checks both ports are released. No extra model process is started for TLS.

After certificate expiry or a LAN IP change, stop the service, rerun setup with the new IP, and restart:

```powershell
.\Stop-SpeechApi.ps1
.\scripts\Setup-Https.ps1 -Address '<server-ip>'
.\Start-SpeechApi.ps1
```

Setup reuses the existing CA and key, so leaf renewal does not require trusting a new CA. It does not modify any certificate trust store. Reserve the PC's IP in the router to keep the address stable. If the CA itself expires, replace it deliberately and repeat client trust setup. `Enable-Lan.ps1` creates a Private/LocalSubnet-only firewall rule for both public ports when run as administrator.

## Browser recording APIs

Capture uses public [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet) and [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) APIs. Audio is emitted directly as WAV, avoiding differences in MediaRecorder container formats and avoiding a new server decoder. A microphone permission promise may remain pending indefinitely; cancellation closes the audio context immediately and stops any stream granted later. Browser verification uses a simulated microphone and normal certificate validation, with no physical microphone access or visible browser.
