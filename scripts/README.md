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
cp scripts/launchd/com.polyhermes.backend-local.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.polyhermes.backend-watchdog.plist ~/Library/LaunchAgents/

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polyhermes.backend-local.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polyhermes.backend-watchdog.plist
```

`backend-local` 通过 `run_backend_local.sh` 加载项目 `.env` 并持续监督 Java 进程。
`backend-watchdog` 每分钟同时检查 Actuator 和一个实际访问数据库仓库的业务接口，连续失败三次后重启 Backend。

已提交的 `V*.sql` Flyway 迁移不可修改。需要调整数据库时必须添加新版本迁移；Backend 构建阶段会运行
`scripts/check-applied-migrations.sh`，检测到旧迁移被修改或删除时拒绝生成新 jar。运行中的 launchd 仍可使用上一个已验证 jar 自动恢复。

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

业务级探针：

```bash
curl -X POST http://localhost:8000/api/auth/check-first-use
# {"code":0,"data":{"isFirstUse":false},"msg":""}
```

Actuator 用于进程存活检查，业务探针覆盖 Spring MVC、拦截器和数据库 Repository。两者都正常才视为 Backend 可用。

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
export POLYBURG_WEB_URL=https://web.telegram.org/a/#7698624735
export POLYBURG_SOURCE_URL=https://web.telegram.org/a/#7698624735
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
POLYBURG_WEB_URL=https://web.telegram.org/a/#7698624735
POLYBURG_SOURCE_URL=https://web.telegram.org/a/#7698624735
```

可以从模板开始：

```bash
cat scripts/polyburg-sync.env.example
```

---

## 6. Kalshi XRP 15m Shadow 验证

每分钟追加一次只读盘口快照：

```bash
python3 scripts/kalshi_xrp15m_shadow.py snapshot
```

运行无未来数据泄漏的七天历史验证：

```bash
python3 scripts/kalshi_xrp15m_shadow.py backtest --lookback-days 7
```

报告写入 `reports/kalshi-xrp15m/latest.md`，原始对齐样本写入同目录的 `latest.json`。安装每分钟采集任务：

```bash
mkdir -p logs data ~/Library/LaunchAgents
cp scripts/launchd/com.polyhermes.kalshi-xrp15m-shadow.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.polyhermes.kalshi-xrp15m-shadow.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polyhermes.kalshi-xrp15m-shadow.plist
```

该任务只写 `data/kalshi-xrp15m-shadow.jsonl`，不会调用交易接口。
