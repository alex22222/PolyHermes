#!/bin/bash
# PolyHermes 本地开发服务统一托管脚本（tmux 版）
# 一个命令启动/停止/查看 backend + frontend + bridge
#
# 用法：
#   ./scripts/tmux-services.sh start    # 启动所有服务
#   ./scripts/tmux-services.sh stop     # 停止所有服务
#   ./scripts/tmux-services.sh attach   # 进入 tmux session
#   ./scripts/tmux-services.sh status   # 查看各服务健康状态

set -euo pipefail

SESSION_NAME="polyhermes"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
mkdir -p "$LOG_DIR"

# 加载项目 .env（如有），用于获取共享密钥
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
fi

export JAVA_HOME="${JAVA_HOME:-$PROJECT_ROOT/jdk17/Contents/Home}"
export PATH="$JAVA_HOME/bin:$PATH"

# 本地开发固定配置
export SERVER_PORT="${SERVER_PORT:-8000}"
export DB_URL="${DB_URL:-jdbc:mysql://localhost:3307/polyhermes?useSSL=false&serverTimezone=UTC&characterEncoding=utf8&allowPublicKeyRetrieval=true}"
export DB_USERNAME="${DB_USERNAME:-root}"
# DB_PASSWORD 优先从 .env 读取；如未设置，必须手工提供
export DB_PASSWORD="${DB_PASSWORD:?DB_PASSWORD is required, set it in .env or environment}"
export SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-prod}"
export BRIDGE_PORT="${BRIDGE_PORT:-8080}"

# 加密/密钥兼容：历史数据用 JWT_SECRET 作为 encryption.key
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-${JWT_SECRET:-}}"
# 本地开发 JWT 密钥，如未设置则使用固定值（仅限本地）
export JWT_SECRET="${JWT_SECRET:-aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899}"
export ADMIN_RESET_PASSWORD_KEY="${ADMIN_RESET_PASSWORD_KEY:-00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff0011223344556677}"
export CRYPTO_SECRET_KEY="${CRYPTO_SECRET_KEY:-234b95c565ef698d0de3f5878a391d7ccc473cb0c6ad1584fb550b75c8f36a48}"
export LOG_LEVEL_APP="${LOG_LEVEL_APP:-INFO}"

backend_log="$LOG_DIR/backend.log"
frontend_log="$LOG_DIR/frontend.log"
bridge_log="$LOG_DIR/bridge.log"

cmd_start() {
    if command -v tmux &>/dev/null && tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' already exists. Run '$0 attach' to view."
        exit 1
    fi

    echo "==> Starting PolyHermes services in tmux session '$SESSION_NAME'"
    echo "    Logs: $LOG_DIR"

    # 1) backend window
    tmux new-session -d -s "$SESSION_NAME" -n backend \
        "cd '$PROJECT_ROOT/backend' && exec java -jar -Dserver.port=$SERVER_PORT build/libs/polyhermes-backend-1.0.0.jar --spring.profiles.active=$SPRING_PROFILES_ACTIVE 2>&1 | tee '$backend_log'"

    # 2) frontend window
    tmux new-window -t "$SESSION_NAME" -n frontend \
        "cd '$PROJECT_ROOT/frontend' && exec npm run dev 2>&1 | tee '$frontend_log'"

    # 3) bridge window
    tmux new-window -t "$SESSION_NAME" -n bridge \
        "cd '$PROJECT_ROOT/polymtrade-bridge' && exec ./start.sh 2>&1 | tee '$bridge_log'"

    echo "==> Services started."
    echo "    Attach : $0 attach"
    echo "    Status : $0 status"
    echo "    Stop   : $0 stop"
}

cmd_stop() {
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' not running."
        return 0
    fi
    echo "==> Stopping PolyHermes services..."
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    # 兜底清理后端和 bridge 残留进程
    pkill -f "polyhermes-backend-1.0.0.jar" 2>/dev/null || true
    pkill -f "python .*polymtrade-bridge/main.py" 2>/dev/null || true
    echo "==> Stopped."
}

cmd_attach() {
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Session '$SESSION_NAME' not running. Start with '$0 start'."
        exit 1
    fi
    exec tmux attach-session -t "$SESSION_NAME"
}

cmd_status() {
    echo "==> Service status"
    printf "%-15s %-10s %-30s\n" "SERVICE" "PID/PORT" "HEALTH"

    # backend
    backend_pid=$(pgrep -f "polyhermes-backend-1.0.0.jar" | head -1 || true)
    if [[ -n "$backend_pid" ]]; then
        health=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$SERVER_PORT/actuator/health" || echo "ERR")
        if [[ "$health" == "200" ]]; then
            status=$(curl -s "http://localhost:$SERVER_PORT/actuator/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
            printf "%-15s %-10s %-30s\n" "backend" "$backend_pid:$SERVER_PORT" "UP ($status)"
        else
            printf "%-15s %-10s %-30s\n" "backend" "$backend_pid:$SERVER_PORT" "HTTP $health"
        fi
    else
        printf "%-15s %-10s %-30s\n" "backend" "-" "NOT RUNNING"
    fi

    # frontend
    frontend_pid=$(pgrep -f "vite" | head -1 || true)
    if [[ -n "$frontend_pid" ]]; then
        printf "%-15s %-10s %-30s\n" "frontend" "$frontend_pid:3000" "RUNNING"
    else
        printf "%-15s %-10s %-30s\n" "frontend" "-" "NOT RUNNING"
    fi

    # bridge
    bridge_pid=$(pgrep -f "python .*polymtrade-bridge/main.py" | head -1 || true)
    if [[ -n "$bridge_pid" ]]; then
        printf "%-15s %-10s %-30s\n" "bridge" "$bridge_pid:$BRIDGE_PORT" "RUNNING"
    else
        printf "%-15s %-10s %-30s\n" "bridge" "-" "NOT RUNNING"
    fi
}

case "${1:-status}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    attach)
        cmd_attach
        ;;
    status)
        cmd_status
        ;;
    *)
        echo "Usage: $0 {start|stop|attach|status}"
        exit 1
        ;;
esac
