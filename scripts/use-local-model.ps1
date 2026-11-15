param(
    [ValidateSet('tutor','reasoner','coder')][string]$Role = 'tutor',
    [Parameter(Mandatory=$true)][string]$Task
)
$models = @{ tutor='qwen3.5:4b'; reasoner='deepseek-r1:1.5b'; coder='qwen2.5-coder:3b' }
$env:LIFEOS_OLLAMA_MODEL = $models[$Role]
if (Get-Command lifeos -ErrorAction SilentlyContinue) {
    lifeos ask ollama $Task
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -m lifeos.cli ask ollama $Task
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m lifeos.cli ask ollama $Task
} else {
    throw 'Python/LifeOS is not available on PATH. Install lifeos-engine first.'
}
