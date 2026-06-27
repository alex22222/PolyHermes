#!/bin/bash
# 加载项目根目录的 .env（包含 DB_PASSWORD/JWT_SECRET 等共享密钥），然后启动后端。
# 如需覆盖某些变量，在 .env 中修改即可。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "ERROR: $SCRIPT_DIR/.env not found. Please copy .env.example to .env and fill in the values." >&2
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$SCRIPT_DIR/.env"
set +a

# 运行必要环境变量检查
"$SCRIPT_DIR/scripts/check-env.sh"

export JAVA_HOME="${JAVA_HOME:-$SCRIPT_DIR/jdk17/Contents/Home}"
export PATH="$JAVA_HOME/bin:$PATH"

# 本地开发固定使用 8000 端口和本地 MySQL 3307
export SERVER_PORT=8000
export DB_URL="jdbc:mysql://localhost:3307/polyhermes?useSSL=false&serverTimezone=UTC&characterEncoding=utf8&allowPublicKeyRetrieval=true"

# 历史加密数据默认使用 JWT_SECRET 作为加密密钥
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-${JWT_SECRET}}"

# 本地开发默认 Bridge webhook
export BRIDGE_WEBHOOK_URL="${BRIDGE_WEBHOOK_URL:-http://localhost:8080/signal}"

cd "$SCRIPT_DIR/backend"
exec java -jar -Dserver.port=$SERVER_PORT build/libs/polyhermes-backend-1.0.0.jar --spring.profiles.active=${SPRING_PROFILES_ACTIVE:-prod}
