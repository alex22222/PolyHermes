# Future BTC5m Bridge 控制页面

2026-10-11。用户已确认每笔金额为平台 **1 美元**，并明确授权自动下单。本次实现项目页面与隔离控制接口；当前缺少 Future 交易执行适配器，尚不能自动提交买入。

## 页面与状态

登录项目后，从侧栏 **Future BTC 5 分钟** 进入 `/future-btc5m-bridge`。

- 固定 BTC 5 分钟、每笔本金 $1；页面不能改变金额或周期。
- 自动下单开关保存 `requestedEnabled`，独立关停按钮始终保留。服务器确认后更新开关，失败显示“状态未知”，不会把超时当作关闭成功。
- `effectiveEnabled` 表示实际执行状态，`executorReady` 表示执行器是否就绪。目前两者均为 `false`，开启请求后显示“受阻，不会下单”。这不是可执行的 Live 开关。
- 每 5 秒刷新状态和订单；15 秒没有新状态显示过期。冻结采样超过 5 秒、超过 +80 秒或轮次不符时，不显示可用于入场的方向。
- 订单列表支持状态筛选、分页和详情抽屉。详情包含轮次、方向、本金、执行事件、平台订单号、实际成交量、均价、费用及提交/成交时间；未知值显示 `—`。

与现有 Bridge 相同，区分信号处理、提交和成交事实。Future 配置与记录单独保存，不写入现有 Bridge 订单表，不复用其浏览器交易队列。

## 链路与接口

```mermaid
flowchart LR
  P[项目受保护页面] --> J[项目 JWT 鉴权 API]
  J --> C[本地 Future 控制服务]
  S[BTC5m 信号助手] --> C
  C --> L[独立控制状态与订单记录]
  C --> B[当前执行器未连接：受阻]
```

项目 API 使用现有 `ApiResponse`，全部要求 JWT：

| 方法与路径 | 请求 |
|---|---|
| `POST /api/future-btc5m/status` | `{}` |
| `POST /api/future-btc5m/control` | 仅 `{"enabled":true/false}` |
| `POST /api/future-btc5m/orders/list` | `{"page":1,"size":20,"status":"SKIPPED"}`，status 可省略 |
| `POST /api/future-btc5m/orders/detail` | `{"id":"future-btc5m:<轮次秒数>"}` |

后端配置项 `future.bridge.url`，默认 `http://127.0.0.1:8766`，可通过 Spring 配置 `FUTURE_BRIDGE_URL` 设置。后端只访问配置的固定桥地址，不转发用户 JWT，不接受调用者提供 URL。响应需通过身份、固定金额、状态一致性、列表及订单事实校验；空响应和无法确认的开关结果都报失败。

本地助手新增 `GET /bridge/status`、`POST /bridge/control`、`GET /bridge/orders`、`GET /bridge/orders/<id>`。控制请求要求专用头 `X-PolyHermes-Future-Control: 1`、严格布尔 JSON、正确本机 Host，并拒绝带 Origin 的浏览器直连；不提供 CORS。现有 `/status`、`/draft` 保持原语义，没有交易提交端点。

## 运行与记录

```bash
cd /Users/henry/projects/polyhermes
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --watch
```

辅助服务监听 `127.0.0.1:8766`。控制状态为 `reports/future-btc5m-assistant/bridge/control.json`，记录为同目录 `orders.jsonl`。重启强制关闭开关并保留历史记录；STOP 自动取消启用请求，损坏账本和写盘失败阻断新的记录。

仅开启请求后，新的有效信号可进入记录：BTC5m 正确轮次、+60 至 +80 秒、新鲜 Chainlink 样本及 60 秒 TWAP 基准。启用前样本不补录，每轮去重一次。目前唯一可能新增的记录是 `SKIPPED / EXECUTOR_NOT_CONNECTED`；提交、成交、平台订单号及费用字段必须为空。读取状态或列表不会生成记录。

项目后端需要与此本机服务同机，或通过私有转发抵达对应 loopback 端点。VPS 中的 `127.0.0.1` 指向 VPS，不能直接连接用户 Chrome 所在 Mac。生产连接使用独立 Unix socket SSH 反向隧道和只监听 app 网络 loopback 的 relay；不发布端口、不复制浏览器登录资料，详见 [生产私有连接](future-btc5m-production-transport.md)。

## 下单前只读预检

扩展 0.2.4 每秒读取当前 BTC5m 页面的轮次、美元市价买入栏、现有金额、已选方向及买入按钮状态，仅将严格白名单字段报告到本机 `POST /bridge/preflight`。该接口要求 `X-PolyHermes-Future-Preflight: 1`，仅接受本机或合法 Chrome 扩展 Origin；报告不包含查询参数、DOM 文本、余额、账户标识或凭据。

项目状态中的 `preflight` 与自动下单开关独立。只有浏览器报告新鲜、市场和票据属于本轮、现有金额 $1、已选方向与真实新鲜 Chainlink/TWAP 信号一致、买入按钮可用且处于 +60 至 +80 秒窗口时，才报告 `READ_ONLY_READY`。它只证明这些只读检查通过，不表示订单提交或成交，也不替代正式交易资格和金额准备守卫。

每轮通过记录仅 fsync 保存一次到独立 `preflight.jsonl`；重启清空当前浏览器连接事实，保留校验通过的历史记录。页面明确区分当前预检与历史通过记录；浏览器或采样过期、断连时不能沿用历史状态作为当前就绪。预检账本损坏或写入失败只阻断预检，不伪造通过记录。

## 验证与剩余工作

当前 172 项测试通过：100 Python、52 Node、20 Kotlin；前端构建、定向 ESLint 和 TypeScript 检查通过。111 项（66 Python、28 Node、17 Kotlin）是历史控制页阶段的测试汇总。后端先有 6 个失败测试复现响应校验缺口，账本拒读修复也先由 3 个失败测试复现，修复后全部通过。账本损坏或写盘未确认时列表/详情报 503，统计显示未知。

真实本地服务只读核对：行情 CURRENT、开关关闭、实际执行关闭、执行器未就绪、0 条记录。界面开启、受阻、跳过详情和关闭操作在独立临时数据中验证；临时数据未进入真实记录，未连接账户或提交交易。报告见 [控制页验收记录](../reports/future-btc5m-assistant/control-page-verification-20261011.json)。

本机提供 [只读预览](http://127.0.0.1:4177/future-preview.html)，渲染实际页面组件，展示真实本地服务状态，控制写入禁用。预览与项目正式 JWT API 分开，不能用本地预览代替生产鉴权与私有连接验收。后续生产验收记录单独保存。

扩展 0.2.4 在真实自然轮次 `1791709800`、`1791709861.343` 时只读预检返回 `READ_ONLY_READY`：方向 Up、页面现有金额 $1、`noSubmission=true`。轮次 `1791711900` 在开盘后 61.391 秒再次通过，记录已显示在生产页面。持续 SPA 页面报告问题已由 `b6e9b90` 修复。导航和现有票据检查已通过；未写入金额、选择方向或提交订单。

后端与前端 `d5464c0` 已上线。`83c2e12` 修复旧 ServiceWorker 的导航缓存，7 项回归通过；`d4c6862` 将专用 relay 上游超时改为 3 秒，18 项 relay 回归通过，生产连续 40 次状态/订单读取全部成功，最慢 1.902 秒。原 Bridge、MySQL 与配置未改，app 健康。

正式 Chrome 页面的鉴权、关闭控制、断线时显示未知、恢复后显示接口已连接和新鲜浏览器报告、当前市场及现有 $1 票据、历史通过记录和空订单列表均已验收。轮次 `1791712200` 的新鲜 Down 信号与页面既有 Up 方向不匹配，真实预检正确返回 `BLOCKED / SIDE_MISMATCH`；没有为通过检查而改方向。完整证据见 [生产只读验收记录](../reports/future-btc5m-assistant/production-preorder-verification-20261011.json) 和 [40 次查询记录](../reports/future-btc5m-assistant/relay-after-d4c6862-20261011.json)。

`e3763db` 修复状态刷新时误闪“运行状态已过期”：状态响应的接收时间与页面时钟同步更新，不再拿上一秒的时钟误判时间回拨。组件回归先复现首次响应、轮询响应、关闭控制响应的 3 项失败；修复后 51 项相关 Node 测试、前端构建和定向 ESLint 通过，真实 15 秒过期、3 秒来源时差、墙钟回拨及信号/预检 5 秒时效守卫保留。

`b3df53b` 增加前台私有隧道断线重连，隧道与 relay 共 36 项 Python 测试通过。生产故障演练只关闭专用 SSH 连接，接口如实返回 503；脚本自动等待 5 秒并安全清理失效 socket 后重连，随后 6 次只读状态请求均成功。正式 Chrome 页面修复后及重连后共 236 次采样，没有运行状态过期误报或状态未知；开关关闭、订单为 0。app 未暂停或重启，原 Bridge、MySQL、JAR 与环境哈希核对一致。详见 [计时修复与恢复验收](../reports/future-btc5m-assistant/ui-clock-fix-verification-20261011.json)。

Mac 助手和前台私有 SSH 隧道仍须持续运行，未安装定时任务或常驻管理器。Chrome 标签页休眠或网络延迟时报告会过期并暂停就绪显示，真实连接失败仍显示错误；本次有界采样不证明后台全天可用。

剩余工作是 Future 交易执行器接入，包括方向与金额写入、交易提交及平台订单/成交核对。本次完成生产只读链路验收，实际开关保持关闭、订单为 0；当前页面不能证明交易步骤已经跑通，原自动下单目标仍未完成。
