[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$config = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'service.psd1')
$runtimeRoot = Join-Path $PSScriptRoot $config.ParakeetRoot
$python = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'scripts\InstallEnvironment.ps1')
$basePython = Initialize-InstallEnvironment $PSScriptRoot
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $python)) {
    & uv venv --relocatable --python $basePython (Join-Path $runtimeRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& uv pip install --python $python torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
$requirements = Join-Path $PSScriptRoot 'requirements-api.lock.txt'
if (-not (Test-Path -LiteralPath $requirements)) { $requirements = Join-Path $PSScriptRoot 'requirements-api.txt' }
& uv pip install --python $python -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'API dependency installation failed.' }
& $python -c 'import sys; from huggingface_hub import snapshot_download; snapshot_download("nvidia/parakeet-tdt-0.6b-v3", revision=sys.argv[1], local_dir=sys.argv[2], token=False, max_workers=3, allow_patterns=["*.json", "model.safetensors", "README.md"])' $config.ParakeetRevision (Join-Path $runtimeRoot 'model')
if ($LASTEXITCODE -ne 0) { throw 'Model download failed; rerun to resume.' }
& $python -c 'import torch; assert torch.cuda.is_available(); print(torch.__version__, torch.cuda.get_device_name(0))'
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed.' }
