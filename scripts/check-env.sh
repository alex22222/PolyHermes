#!/bin/bash
# 检查 PolyHermes 必要环境变量是否已配置。
# 用法：source scripts/check-env.sh

set -euo pipefail

check_required() {
    local name="$1"
    local value="${!name:-}"
    if [[ -z "$value" ]]; then
        echo "ERROR: $name is required. Set it in .env or export it before starting services." >&2
        return 1
    fi
}

check_not_default() {
    local name="$1"
    local value="${!name:-}"
    local defaults=("change-me-in-production" "your-secret-key-change-in-production" "rootpassword" "11111111" "test-jwt-secret-key-for-testing-only" "test-reset-key-for-testing-only")
    for d in "${defaults[@]}"; do
        if [[ "$value" == "$d" ]]; then
            echo "WARNING: $name is using default/unsafe value '$value'. Please change it in .env." >&2
            return 1
        fi
    done
}

fail=0

for var in JWT_SECRET ADMIN_RESET_PASSWORD_KEY DB_PASSWORD CRYPTO_SECRET_KEY; do
    if ! check_required "$var"; then
        fail=1
    fi
done

for var in JWT_SECRET ADMIN_RESET_PASSWORD_KEY DB_PASSWORD CRYPTO_SECRET_KEY; do
    if ! check_not_default "$var"; then
        fail=1
    fi
done

if [[ "$fail" -ne 0 ]]; then
    echo "Environment validation failed. Please fix your .env and try again." >&2
    exit 1
fi

echo "Environment validation passed."
