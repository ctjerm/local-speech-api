[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$config = Import-PowerShellDataFile (Join-Path $projectRoot 'service.psd1')
$runtimeRoot = Join-Path $projectRoot $config.RuntimeRoot
$source = Join-Path $runtimeRoot 'upstream'
$python = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
Get-Command uv, git -ErrorAction Stop | Out-Null
. (Join-Path $PSScriptRoot 'InstallEnvironment.ps1')
$basePython = Initialize-InstallEnvironment $projectRoot
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $source)) {
    & git clone https://github.com/breezeblue-ai/breeze-tts.git $source
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone upstream.' }
}
$changes = & git -C $source status --porcelain
if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Upstream checkout must be a clean Git checkout; preserve local edits before installing.' }
& git -C $source fetch origin $config.UpstreamCommit
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the pinned source revision.' }
& git -C $source checkout --detach $config.UpstreamCommit
if ($LASTEXITCODE -ne 0) { throw 'Could not select the pinned source revision.' }

if (-not (Test-Path -LiteralPath $python)) {
    & uv venv --relocatable --python $basePython (Join-Path $runtimeRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& uv pip install --python $python torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
& uv pip install --python $python -r (Join-Path $projectRoot 'requirements\requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Runtime dependency installation failed.' }
& $python -c 'import sys; from huggingface_hub import snapshot_download; snapshot_download("BreezeBlue/Breeze-TTS-2", revision=sys.argv[1], local_dir=sys.argv[2], token=False, max_workers=3, ignore_patterns=["assets/*"])' $config.ModelRevision (Join-Path $runtimeRoot 'model')
if ($LASTEXITCODE -ne 0) { throw 'Model download failed; rerun to resume.' }
& $python -c 'import torch; assert torch.cuda.is_available(), "CUDA GPU unavailable"; x=torch.ones(4, device="cuda"); assert x.sum().item()==4; print(torch.__version__, torch.cuda.get_device_name(0))'
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed.' }
Write-Output "Breeze installed in $runtimeRoot."
