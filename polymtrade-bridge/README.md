# PolyHermes → Polymtrade Bridge

自动桥接系统：PolyHermes 检测到 Leader 交易信号 → 通过 HTTP webhook 发送给 Bridge Service → Bridge 通过浏览器自动化在 Polymtrade 上执行跟单。

## 架构

```
PolyHermes (检测 Leader)
    │
    ▼
HTTP webhook → POST /signal
    │
    ▼
Bridge Service (FastAPI + Playwright)
    │
    ▼
Polymtrade Web UI (自动下单)
```

## 文件说明

- `main.py` — FastAPI 服务，接收 `/signal` 信号并调度执行
- `polymtrade_executor.py` — Playwright 浏览器自动化
- `bridge_recorder.py` — 记录交易执行结果到 PolyHermes 数据库
- `Dockerfile` / `docker-compose.yml` — 容器化部署

## 快速开始（本地运行）

### 1. 安装依赖

```bash
cd polymtrade-bridge
./run_local.sh
```

### 2. 登录 Polymtrade

首次运行会打开浏览器窗口，访问 https://polym.trade。请手动完成登录（Privy 邮箱/钱包）。登录状态会保存在 `browser_profile/` 目录。

### 3. 配置 PolyHermes Webhook

在启动 PolyHermes 后端前设置环境变量：

```bash
export BRIDGE_WEBHOOK_URL='http://localhost:8080/signal'
```

当 PolyHermes 检测到 Leader 交易时，会直接 POST 到 Bridge 的 `/signal` 端点，Bridge 自动在 Polymtrade 上执行买入/卖出。

### 4. 查看执行结果

前端 **桥接交易记录** 页面可查看每条信号的下单结果；**Webhook 日志** 标签页可查看 PolyHermes 向后端/Bridge 发送信号的调用记录。

## Docker 部署

```bash
cd polymtrade-bridge
docker-compose up -d
```

注意：Docker 模式下 `HEADLESS=false` 无法显示 GUI，建议先在本地完成登录并复制 `browser_profile` 到容器 volume，或配置 VNC。

## 配置

复制 `.env.example` 为 `.env` 并修改：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `POLYMTRADE_URL` | Polymtrade 地址 |
| `BROWSER_PROXY` | 浏览器代理，如 `http://host.docker.internal:7890` |
| `HEADLESS` | 是否无头模式 |
| `BROWSER_PROFILE_DIR` | 浏览器 profile 目录 |

## 注意事项

1. **首次登录必须手动完成**：Privy 认证无法完全自动化
2. **Polymtrade UI 可能变化**：需要根据实际情况调整 `polymtrade_executor.py` 中的选择器
3. **建议先用小额测试**：默认单笔金额为 1 USDC，可在 `main.py` 中修改
4. **地区限制**：Bridge 浏览器代理需使用 Polymtrade 可用的地区 IP
