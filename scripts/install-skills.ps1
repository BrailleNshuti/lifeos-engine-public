# Copies the Engine's skills to Claude Code, Codex and Antigravity/Gemini (user level). Re-run after every update.
$src = Join-Path $PSScriptRoot "..\skills"
foreach ($dest in @("$HOME\.claude\skills", "$HOME\.codex\skills", "$HOME\.gemini\config\skills")) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Copy-Item -Recurse -Force "$src\*" $dest
  Write-Output "skills -> $dest"
}
