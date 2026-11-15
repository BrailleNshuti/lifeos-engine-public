param([switch]$InstallRuntime)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (-not $InstallRuntime) {
        throw 'Ollama is not installed. Re-run with -InstallRuntime to install the official Windows package.'
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is required for the audited Ollama installation path.'
    }
    winget install --id Ollama.Ollama --exact --scope user --accept-package-agreements --accept-source-agreements
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'
    if (Test-Path -LiteralPath $candidate) { $env:Path = "$candidate;$env:Path" }
}

$models = @('qwen3.5:4b', 'deepseek-r1:1.5b', 'qwen2.5-coder:3b')
foreach ($model in $models) {
    Write-Host "Pulling $model ..."
    ollama pull $model
}
ollama list
Write-Host 'Ready: tutor=qwen3.5:4b, reasoner=deepseek-r1:1.5b, coder=qwen2.5-coder:3b'
