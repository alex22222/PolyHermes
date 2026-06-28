#!/bin/bash
# PolyHermes local Java runtime resolver.
# Usage: source scripts/java-env.sh

set -euo pipefail

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_PATH="${BASH_SOURCE[0]}"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
    SCRIPT_PATH="${(%):-%x}"
else
    SCRIPT_PATH="$0"
fi

SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

JAVA_HOME_CANDIDATES=(
    "${JAVA_HOME:-}"
    "$HOME/.jdk17/Contents/Home"
    "$PROJECT_ROOT/jdk17/Contents/Home"
)

for candidate in "${JAVA_HOME_CANDIDATES[@]}"; do
    if [[ -n "$candidate" && -x "$candidate/bin/java" ]]; then
        export JAVA_HOME="$candidate"
        export PATH="$JAVA_HOME/bin:$PATH"
        return 0 2>/dev/null || exit 0
    fi
done

echo "ERROR: Java 17 runtime not found. Expected one of:" >&2
echo "  $HOME/.jdk17/Contents/Home" >&2
echo "  $PROJECT_ROOT/jdk17/Contents/Home" >&2
return 1 2>/dev/null || exit 1
