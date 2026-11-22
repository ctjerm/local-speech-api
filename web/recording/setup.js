try {
  const config = await (await fetch("/site-config")).json();
  if (!config.local_certificate) throw new Error("This server has no local certificate configured. Ask the server owner to run Setup-Https.ps1.");
  document.getElementById("certificate-status").textContent = "Certificate name: Voice room Local CA";
  document.getElementById("certificate-fingerprint").textContent = config.ca_sha256;
  if (config.https_port) {
    const url = new URL(location.origin);
    url.protocol = "https:";
    url.port = config.https_port;
    const link = document.getElementById("open-secure-studio");
    link.href = url.href;
    link.hidden = false;
  }
} catch (error) {
  document.getElementById("certificate-status").textContent = error.message;
  document.getElementById("certificate-download").hidden = true;
}
