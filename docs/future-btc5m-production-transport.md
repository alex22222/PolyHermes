# Future BTC 5 分钟生产私有连接

生产网页和 Kotlin API 在 VPS，Future Chrome 登录与助手在用户 Mac。VPS、Docker 容器和 Mac 各自的 `127.0.0.1` 不相通，需要独立的私有传输。此组件仅传输已允许的助手接口，没有交易提交适配器。

```text
生产网页 → 已鉴权 Kotlin API → 同网络命名空间 127.0.0.1:8766 relay
                                     ↓ 固定 Unix socket
             /opt/polyhermes/future-btc5m/assistant.sock
                                     ↓ SSH reverse Unix socket tunnel
                         Mac 127.0.0.1:8766 assistant
```

## 运行前提

- Mac 助手已运行，`GET http://127.0.0.1:8766/status` 正常，金额固定为平台 $1。
- 生产目录 `/opt/polyhermes/future-btc5m` 单独建立，属主 root、权限 `0700`。仅放入已审阅的 `future_btc5m_relay.py` 和本传输专用的 `assistant.sock`。
- 生产镜像 `polyhermes-app:jev-d10fe23` 已有 Python 3 标准库，无需安装包或构建新镜像。
- Kotlin 客户端仍使用 `http://127.0.0.1:8766`。relay 必须共享 app 网络命名空间。

此文档的命令是操作说明；新增文件本身不会部署、建立 SSH 连接或启用自动下单。

## 启动顺序

在 Mac 前台运行，仅使用现有 SSH key 和已知主机：

```bash
bash scripts/start-future-btc5m-tunnel.sh
```

SSH 使用 `ExitOnForwardFailure=yes`、存活检测、固定远端 Unix socket，**不开放任何远端 TCP 端口**，不修改 sshd，也不复制 Chrome 登录资料。`StreamLocalBindUnlink=no` 会拒绝覆盖已有 socket；脚本不会停止其他隧道。

确认旧隧道已经结束且只剩失效 socket 时，可显式恢复：

```bash
bash scripts/start-future-btc5m-tunnel.sh --remove-stale-socket
```

恢复仅针对 `/opt/polyhermes/future-btc5m/assistant.sock`，要求路径为 Unix socket、连接报 `ECONNREFUSED`，且检查期间 inode 未变。活动 socket、其他错误、普通文件及符号链接都会拒绝清理。

在 VPS 上启动独立 relay。目录和 Python 文件应先通过审阅的部署流程准备：

```bash
docker run -d --name future-btc5m-relay \
  --network container:polyhermes \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user 0:0 \
  --mount type=bind,src=/opt/polyhermes/future-btc5m,dst=/bridge,readonly \
  --entrypoint python3 \
  polyhermes-app:jev-d10fe23 \
  /bridge/future_btc5m_relay.py --socket /bridge/assistant.sock
```

没有 `-p` 发布端口。root 身份仅用于连接 root 专用 socket；容器 root filesystem 和 `/bridge` 挂载均只读，所有 capabilities 删除。命令直接执行标准库 relay，不执行 app 启动脚本，也不挂载数据库、原 Bridge 或浏览器目录。

## 接口边界与失败状态

relay 只监听 `127.0.0.1:8766`，入站 Host 必须准确匹配，转发到 Mac 时 Host 固定为 `127.0.0.1:8766`。允许：

- GET `/status`、`/draft`、`/bridge/status`、`/bridge/orders`，及严格匹配的 Future 订单详情路径。
- POST `/bridge/control`，要求 `X-PolyHermes-Future-Control: 1`、JSON 对象和不超过 256 字节的请求体。
- POST `/bridge/preflight`，要求 `X-PolyHermes-Future-Preflight: 1`、JSON 对象和不超过 1500 字节的请求体，与本机只读报告接口一致。

拒绝所有 Origin、重复关键头、Transfer-Encoding、任意目标与 `/submit`。不转发 Cookie、Authorization、Set-Cookie 或 CORS。请求和上游操作超时为 2 秒，响应最大 1 MiB。

隧道缺失、断开、超时或上游响应不完整时，返回 HTTP 503 和 `FUTURE_TUNNEL_UNAVAILABLE`，不会制造在线、已关闭、准备成功或成交数据。上游有效的非 200 状态保留。预检查及开关的业务限制仍由本机助手和已鉴权 Kotlin API 执行。

## app 重启和重建

`--network container:polyhermes` 关联容器网络命名空间。app 重启后，应重新启动 relay 并验证两个容器的网络命名空间；**app 被重新创建后，必须重新创建 relay**，不能继续使用指向旧 app 容器的 sidecar。

```bash
docker exec polyhermes readlink /proc/self/ns/net
docker exec future-btc5m-relay readlink /proc/self/ns/net
docker exec polyhermes python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8766/bridge/status", timeout=3).status)'
```

两个 namespace 标识应一致。最后一条仅读取状态；上线验证还应通过项目鉴权 API 验证状态、订单查询与预检查。测试期间保持自动下单关闭，实际提交和成交字段保持空值。

## 本地验证

```bash
scripts/future-btc5m-runtime/.venv/bin/python -m unittest scripts/test_future_btc5m_relay.py -q
bash -n scripts/start-future-btc5m-tunnel.sh
```

测试只使用临时 Unix socket 和随机 loopback 端口，不建立生产 SSH、不读取账户凭据、不发订单。
