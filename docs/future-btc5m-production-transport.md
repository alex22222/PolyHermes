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

脚本本身在前台监督 SSH；下文的 LaunchAgent 可将它交给 macOS 常驻管理。首次本机助手不可用时立即退出；默认首次启动发现已有 socket 也会拒绝，只有上述显式选项允许首次清理。启动后 SSH 以 255 断线时，按 5、10、20、30 秒退避重连，之后等待上限保持 30 秒。每次重连前沿用相同固定路径、socket 类型、`ECONNREFUSED` 和 inode 校验，只清理确认失效的 socket；活动 socket 或远端校验的其他错误会立即停止。校验 SSH 自身连接失败也退避重试，不放宽首次清理规则。Ctrl-C 或 TERM 会结束当前子 SSH/等待进程并停止重连；SSH 正常退出或其他非 255 退出也会结束脚本。单独运行时，关闭这个前台进程仍会使生产接口返回 503。

直连 22 端口不稳定时（2026-10-12 实测：直连握手卡在密钥交换后超时，而经本机代理 3 次均约 3 秒连上），让两条 SSH 都经本机 SOCKS5 代理：

```bash
bash scripts/start-future-btc5m-tunnel.sh --remove-stale-socket --socks-proxy 127.0.0.1:7890
```

参数只接受 `127.0.0.1:端口`，用 `nc -X 5` 作为 `ProxyCommand`，其余 SSH 选项与转发路径不变。隧道断线后，VPS 上旧的 sshd 会话可能仍占用 socket；此时项目页请求会卡住，脚本也会报 `tunnel socket is active`。只关闭 `ss -xlp` 显示持有该 socket 的那个 sshd 进程，再按上面的命令恢复。

## macOS 常驻隧道

专用配置为 `scripts/launchd/com.polyhermes.future-btc5m-tunnel.plist`，沿用项目 LaunchAgent 方式和当前用户的固定路径。`RunAtLoad=true` 在登录时启动，`KeepAlive=true` 在监督脚本任意退出后重新启动；`ThrottleInterval=15` 限制频繁重启。`AbandonProcessGroup=false` 让 launchd 在监督进程被强制结束时清理其 SSH 子进程，避免留下本机孤儿连接。脚本内部的 SSH 退避与 socket 校验保持原样。

隧道配置只启动既有隧道，明确传入 `--remove-stale-socket --socks-proxy 127.0.0.1:7890`。自动恢复仍拒绝覆盖活动 socket、符号链接、普通文件、权限错误或检查期间变化的 inode。Mac 助手或本机代理暂未启动时，launchd 会限速重试，依赖恢复后重新连接；隧道本身不设置助手自启、下单重试或开关修改。

安装前应关闭自动买入并正常结束已有前台隧道，避免两份进程竞争。安装命令：

```bash
mkdir -p reports/future-btc5m-assistant/tunnel ~/Library/LaunchAgents
install -m 600 scripts/launchd/com.polyhermes.future-btc5m-tunnel.plist ~/Library/LaunchAgents/com.polyhermes.future-btc5m-tunnel.plist
launchctl enable gui/$(id -u)/com.polyhermes.future-btc5m-tunnel
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.polyhermes.future-btc5m-tunnel.plist
```

状态：`launchctl print gui/$(id -u)/com.polyhermes.future-btc5m-tunnel`。输出日志为 `reports/future-btc5m-assistant/tunnel/stdout.log` 和 `stderr.log`，不记录账户令牌或行情载荷。暂停服务必须使用 `launchctl bootout gui/$(id -u)/com.polyhermes.future-btc5m-tunnel`，单独杀进程会自动恢复；如需禁止下次登录启动，另执行 `launchctl disable gui/$(id -u)/com.polyhermes.future-btc5m-tunnel`。文件保留用于再次启用。

这是用户登录会话的常驻服务，退出登录、关机、睡眠、代理失效或远端网络异常仍会断联；网络故障恢复有退避时间，不能承诺零断联或绝不漏单。进程故障验收需分别验证 SSH 子进程结束和监督进程被强制结束后自动恢复，再核对生产状态/订单只读接口与正式鉴权页面。测试期间保持自动买入关闭，并核对控制文件和买入审计哈希不变。

2026-10-14 已安装并完成真实故障验收：结束 SSH 子进程、强制结束监督进程后，生产状态与订单接口都从 503 自动恢复为 200，核对恢复时间上界分别为 13.950 秒和 12.663 秒；旧 SSH 子进程已清理，正式页面显示在线与保存开关关闭。41 项隔离测试通过，控制文件及买入审计哈希未变，自动买入保持关闭。登录自启已配置，但没有实际退出登录测试。详见 [常驻隧道验收](../reports/future-btc5m-assistant/tunnel-daemon-20261014/REVIEW.md)。

随后出现隧道仍在线、Mac 助手退出导致 8766 拒绝连接的问题，已增加独立 `com.polyhermes.future-btc5m-assistant` LaunchAgent，补齐上游服务自启和退出恢复。它沿用既有重启关闭买入和撤销旧票据规则；真实退出后 HTTP 服务与浏览器报告在 1.024 秒内恢复。详见 [助手常驻说明](future-btc5m-assistant.md#安装与使用) 和 [验收记录](../reports/future-btc5m-assistant/assistant-daemon-20261014/REVIEW.md)。

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

拒绝所有 Origin、重复关键头、Transfer-Encoding、任意目标与 `/submit`。不转发 Cookie、Authorization、Set-Cookie 或 CORS。入站请求超时为 2 秒，上游 socket 超时为 3 秒，仍小于 Kotlin 客户端的 4 秒总预算；响应最大 1 MiB。生产实测曾出现 2 秒上游截止造成的间歇 503，因此仅增加上游等待时间；报告 3 秒时差、样本 5 秒新鲜度及入场窗口守卫不变。

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
scripts/future-btc5m-runtime/.venv/bin/python -m unittest scripts/test_future_btc5m_tunnel.py -q
scripts/future-btc5m-runtime/.venv/bin/python -m unittest scripts/test_future_btc5m_launchd.py -q
bash -n scripts/start-future-btc5m-tunnel.sh
```

测试只使用临时 Unix socket 和随机 loopback 端口。隧道行为测试用独立 mock SSH、curl、sleep 和临时 key 路径，验证断线重连、退避、拒绝活动 socket 和信号退出，不建立生产 SSH、不读取账户凭据、不发订单。

## 2026-10-11 生产验收

后端和前端发布 `d5464c0`，ServiceWorker 导航缓存修复 `83c2e12`，宿主与专用 relay 内的上游超时修复 `d4c6862` SHA256 均为 `9f58a7f4c97ef9bc8791b2a80db6455e40e62bededece1f44d2832de326a6819`。页面计时修复 `e3763db` 已上线，最新静态文件固化为镜像 `polyhermes-app:future-e3763db`（基于此前的 `future-83c2e12`，离线构建，app 未暂停或重启）；重新创建 app 时须明确选用最新镜像，并按上文重建 relay。没有修改现有 compose 或环境配置。

原 JAR 和前端备份分别位于 `/opt/polyhermes/backups/app-before-future-d5464c0-20261011.jar`、`/opt/polyhermes/backups/frontend-before-future-d5464c0-20261011.tar.gz`；relay 旧文件保留在独立目录的 `relay-before-d4c6862.py`。89 项现有迁移清单一致，没有新增迁移或数据库操作。固化 app 镜像时曾因容器短暂暂停导致健康检查失败，随后自行恢复 healthy，未再次重启 app。

断开专用隧道时 relay 返回 503，正式页面显示状态未知；恢复后正式鉴权页面显示接口已连接、新鲜浏览器报告、当前 $1 票据和空订单列表。超时修复后的 40 次实际状态/订单读取全部 HTTP 200，最慢 1.902 秒；开关与实际执行均关闭、0 订单。证据见 [生产只读验收记录](../reports/future-btc5m-assistant/production-preorder-verification-20261011.json)。这只是本次有界采样，不能证明全天网络稳定；Mac 助手和前台隧道仍是运行依赖。

前台重连修复 `b3df53b` 已实际运行。专用 SSH 故障演练时 relay 返回 503，脚本随后自动退避和安全恢复，新监听进程建立后 6 次状态查询全部成功；原 Bridge、MySQL、app 启动时间及保护文件哈希未变。最新前端备份为 `/opt/polyhermes/backups/frontend-before-future-e3763db-20261011.tar.gz`。详见 [计时修复与恢复验收](../reports/future-btc5m-assistant/ui-clock-fix-verification-20261011.json)。
