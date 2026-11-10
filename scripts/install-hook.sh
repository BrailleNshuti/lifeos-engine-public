#!/usr/bin/env bash
# Usage: scripts/install-hook.sh /path/to/repo  -> installs the privacy guard as that repo's pre-commit hook.
set -euo pipefail
repo="${1:-.}"
install -m 755 "$(dirname "$0")/../hooks/pre-commit" "$repo/.git/hooks/pre-commit"
echo "privacy guard installed in $repo"
