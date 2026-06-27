# PolyHermes 服务托管脚本

本目录提供后端、Bridge 的进程守护与健康检查方案。

---

## 1. 本地开发：tmux 统一托管

```bash
./scripts/tmux-services.sh start    # 启动 backend + frontend + bridge
./scripts/tmux-services.sh status   # 查看健康状态
./scripts/tmux-services.sh attach   # 进入 tmux session
./scripts/tmux-services.sh stop     # 停止所有服务
```

要求：
- `tmux` 已安装
- `.env` 中已配置 `DB_PASSWORD` 等必要变量
- 后端 jar 已构建：`backend/build/libs/polyhermes-backend-1.0.0.jar`
- 前端依赖已安装：`frontend/node_modules`

`status` 子命令会访问 `/actuator/health` 检查后端存活状态。

---

## 2. macOS：launchd

```bash
mkdir -p ~/Library/LaunchAgents
cp scripts/launchd/com.polyhermes.backend.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.polyhermes.bridge.plist ~/Library/LaunchAgents/

# 编辑 plist，把 SET_FROM_ENVIRONMENT 替换为真实值
launchctl load ~/Library/LaunchAgents/com.polyhermes.backend.plist
launchctl load ~/Library/LaunchAgents/com.polyhermes.bridge.plist
```

---

## 3. Linux：systemd

```bash
sudo cp scripts/systemd/polyhermes-backend.service /etc/systemd/system/
sudo cp scripts/systemd/polyhermes-bridge.service /etc/systemd/system/

# 创建环境文件 /etc/polyhermes/backend.env 与 /etc/polyhermes/bridge.env
sudo systemctl daemon-reload
sudo systemctl enable --now polyhermes-backend
sudo systemctl enable --now polyhermes-bridge
```

---

## 4. 健康检查

后端已启用 Spring Boot Actuator：

```bash
curl http://localhost:8000/actuator/health
# {"status":"UP"}
```

所有守护方案都建议把该端点作为存活检查（liveness probe）。
