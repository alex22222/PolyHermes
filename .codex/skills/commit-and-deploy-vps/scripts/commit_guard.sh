#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "Not inside a Git repository" >&2
  exit 1
fi

forbidden='(^|/)(\.env|\.env\..*|browser_profile|.*\.sqlite3?|.*\.db|logs?/|node_modules/|backend/build/|frontend/dist/|\.ssh/)(/|$)'
files=$(git diff --cached --name-only --diff-filter=ACMRTUXB)
if [[ -z "$files" ]]; then
  echo "No staged files; stage reviewed paths first." >&2
  exit 1
fi

if printf '%s\n' "$files" | grep -E "$forbidden"; then
  echo "Refusing staged secret/runtime paths" >&2
  exit 1
fi

if printf '%s\n' "$files" | grep -E '(^|/)(id_rsa|.*\.pem|.*\.key)$'; then
  echo "Refusing staged private key files" >&2
  exit 1
fi

echo "Commit guard passed for $(printf '%s\n' "$files" | wc -l | tr -d ' ') staged path(s)."
