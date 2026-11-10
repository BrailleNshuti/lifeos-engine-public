#!/usr/bin/env bash
# Copies the Engine's skills to Claude Code and Codex (user level). Re-run after every update.
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)/skills"
for dest in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$dest"
  cp -R "$src"/. "$dest"/
  echo "skills -> $dest"
done
