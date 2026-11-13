# Installs the privacy guard as a git pre-commit hook in a target repo (default: current folder).
param([string]$Repo = ".")
$hooks = Join-Path (Resolve-Path $Repo) ".git\hooks"
if (-not (Test-Path $hooks)) {
  Write-Error "Not a git repository: $Repo"
  exit 1
}
$target = Join-Path $hooks "pre-commit"
Copy-Item -Force (Join-Path $PSScriptRoot "..\hooks\pre-commit") $target
Write-Output "installed -> $target"
