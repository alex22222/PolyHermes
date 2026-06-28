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

### Java Runtime

本机可用的 Java 17 runtime 固定在：

```bash
/Users/henry/.jdk17/Contents/Home
```

仓库内也可能存在备用 runtime：

```bash
/Users/henry/projects/polyhermes/jdk17/Contents/Home
```

手动运行 Gradle 前先加载统一环境：

```bash
source scripts/java-env.sh
cd backend
./gradlew test
```

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

---

## 5. Polyburg Telegram Leader 自动同步

`sync_polyburg_telegram.py` 使用 Telegram user session 读取 Polyburg bot 新消息，并调用 PolyHermes 的
`/api/copy-trading/leader-research/polyburg-telegram/import` 接口导入候选 leader。导入只进入 Leader Research
候选池，不会自动开启真钱跟单。

如果 Telegram API app 创建失败，也可以用 Web fallback：

```bash
python3 scripts/sync_polyburg_web.py --setup --dry-run
```

这个命令会打开一个独立 Chromium profile。你只需要在弹出的 Telegram Web 里登录并打开 Polyburg bot 聊天，然后回到终端按 Enter。之后 profile 会保存登录态，`run-polyburg-sync.sh` 可以用 headless 模式定时读取。

安装依赖：

```bash
python3 -m pip install telethon playwright
```

第一次运行前，先在 <https://my.telegram.org/apps> 创建 Telegram API 应用，然后设置环境变量：

```bash
export TELEGRAM_API_ID=123456
export TELEGRAM_API_HASH=your_api_hash
export POLYHERMES_BASE_URL=http://127.0.0.1:8000

# 二选一：直接给 JWT，或让脚本登录获取 JWT
export POLYHERMES_TOKEN=your_jwt
# export POLYHERMES_USERNAME=admin
# export POLYHERMES_PASSWORD=your_password
```

先 dry-run：

```bash
python3 scripts/sync_polyburg_telegram.py --dry-run --limit 20
```

确认解析结果后正式导入，并推进本地游标：

```bash
python3 scripts/sync_polyburg_telegram.py --import --limit 50
```

可选环境变量：

```bash
export TELEGRAM_SESSION=.polyburg_telegram
export POLYBURG_TELEGRAM_PEER=7698624735
export POLYBURG_SYNC_STATE=.polyburg_telegram_sync_state.json
export POLYBURG_DEFAULT_CATEGORY=finance
export POLYBURG_AUTO_INSTALL_DEPS=false
export POLYBURG_SYNC_MODE=web
export POLYBURG_PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
export POLYBURG_WEB_PROFILE=/Users/henry/projects/polyhermes/.polyburg_web_profile
export POLYBURG_WEB_SYNC_STATE=/Users/henry/projects/polyhermes/.polyburg_web_sync_state.json
```

cron 示例：

```cron
*/15 * * * * cd /Users/henry/projects/polyhermes && /usr/bin/env bash -lc 'source .env && python3 scripts/sync_polyburg_telegram.py --import >> logs/polyburg-sync.log 2>&1'
```

macOS launchd 示例：

```bash
chmod +x scripts/run-polyburg-sync.sh scripts/sync_polyburg_telegram.py scripts/sync_polyburg_web.py
cp scripts/launchd/com.polyhermes.polyburg-sync.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.polyhermes.polyburg-sync.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.polyhermes.polyburg-sync.plist
tail -f logs/polyburg-sync.log
```

`sync_polyburg_telegram.py` 会自动读取项目 `.env`，所以定时任务不需要手动 export。`.env` 至少需要配置：

```bash
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
POLYHERMES_BASE_URL=http://127.0.0.1:8000
POLYHERMES_TOKEN=your_jwt
POLYBURG_SYNC_MODE=web
POLYBURG_PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
```

可以从模板开始：

```bash
cat scripts/polyburg-sync.env.example
```
