#!/bin/bash
# Existing versioned Flyway migrations are immutable. Add a new migration instead.

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
MIGRATION_PATH="backend/src/main/resources/db/migration"

if ! git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "WARNING: Git worktree unavailable; skipped migration immutability check." >&2
    exit 0
fi

changed=$(
    {
        git -C "$PROJECT_ROOT" diff --name-only --diff-filter=MDR -- "$MIGRATION_PATH/V"'*.sql'
        git -C "$PROJECT_ROOT" diff --cached --name-only --diff-filter=MDR -- "$MIGRATION_PATH/V"'*.sql'
    } | sort -u
)

if [[ -n "$changed" ]]; then
    echo "ERROR: Existing Flyway migrations were modified or removed:" >&2
    echo "$changed" | sed 's/^/  - /' >&2
    echo "Restore these files and add a new V<number> migration instead." >&2
    exit 1
fi

echo "Flyway migration immutability check passed."
