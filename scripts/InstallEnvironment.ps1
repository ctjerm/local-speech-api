function Initialize-InstallEnvironment([string]$projectRoot) {
    $scratch = Join-Path $projectRoot 'runtime\scratch'
    New-Item -ItemType Directory -Path "$scratch\temp", "$scratch\uv-cache" -Force | Out-Null
    $env:TEMP = "$scratch\temp"
    $env:TMP = $env:TEMP
    $env:UV_CACHE_DIR = "$scratch\uv-cache"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot 'runtime\python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $projectRoot 'runtime\bin'
    $env:HF_HOME = "$scratch\huggingface"
    $env:HF_HUB_DISABLE_XET = '1'
    $env:HF_HUB_OFFLINE = '0'
    $env:TRANSFORMERS_OFFLINE = '0'
    & uv python install 3.12.8 --no-bin
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the dedicated Python runtime.' }
    return Join-Path $env:UV_PYTHON_INSTALL_DIR 'cpython-3.12.8-windows-x86_64-none\python.exe'
}
