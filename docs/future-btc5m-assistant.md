# Future BTC 5 分钟辅助桥：固定 $1，用户手动提交

日期：2026-10-11（北京时间）。配套策略见 [周末 BTC 顺势策略](weekend-btc-updown-momentum-strategy.md)。

## 实现范围

用户已确认“每次 1 元”指 Future 的美元金额 1。助手固定订单本金为 **$1**，没有金额放大、人民币换算、倍投或自动补单。官方订单说明将 BUY 金额定义为美元本金，费用可能额外收取；最终扣款与最低订单要求以 Future 页面为准。[Polymarket 订单说明](https://docs.polymarket.com/trading/place-orders)

实现由独立 Python 信号服务和 Chrome 扩展组成。扩展使用用户已登录的 Future 标签页，不读取 Cookie、私钥或登录令牌，不复制浏览器 profile。Python 服务不引用现有 Bridge，不连接项目数据库，仅监听 `127.0.0.1:8766`。

```mermaid
flowchart LR
  A[公开 Gamma / TWAP 开盘价 / Chainlink] --> B[本地信号服务]
  B --> C[Future 页面辅助扩展]
  C --> N[旧 BTC5m 轮次结束后自动前往实时市场]
  N --> P[核对当前 URL 并只读检查金额栏]
  P --> D[显示方向和轮次]
  D --> E[用户点击 填入 $1 草稿]
  E --> F[用户选择涨或跌并核对]
  F --> G[用户点击 Future 买入]
```

已接入自动换轮和只读页面检查；金额草稿仍须符合下面的全部守卫。代码没有提交交易、点击方向或买入按钮、钱包签名、交易 POST 或 Live 开关。真实交易的最终操作必须由用户完成。方向按钮可能兼具极速交易功能，因此扩展仅提示方向。

### 自动换轮步骤

1. 每秒读取本地状态，只在 `ASSIST_ONLY`、固定 $1、服务时间与本机相差不超过 3 秒、服务轮次等于当前 UTC 300 秒轮次时工作。STOP、离线、陈旧状态或其它资产/周期页面会暂停。
2. 只有已结束的 Future BTC5m 页面才点击唯一可见、未禁用、文本精确为“前往实时市场”的按钮。当前轮次不点击；未找到按钮则等待页面更新，不使用其它交易控件作为替代。
3. 点击前在当前标签页的自有 sessionStorage key `polyhermes.future-btc5m.navigation` 记录目标。每个目标轮次最多尝试一次，跨页面重新加载仍去重；10 秒未到达则提示手动检查“前往本轮市场”。不读取其它存储键或登录信息。
4. 到达当前轮次 URL，且旧的实时市场按钮已消失后，自动只读检查金额栏；同一个票据容器的英文市场标题必须匹配本轮的美东日期和五分钟范围。URL 切换或旧轮结束时清除之前的检查；页面尚未渲染完成则等待，不把旧票据当作新轮通过。
5. 换页仅浏览公开市场，因此不依赖金额准备资格；它不会放行金额守卫。`GEOBLOCK_BLOCKED` 或 Future 资格 `UNKNOWN` 时仍可换页，但金额按钮保持禁用。面板分别显示换轮结果、页面检查和信号/资格状态。

## 策略与拒绝条件

- 仅美东周六/周日开盘的 BTC 5 分钟轮次，按 UTC 300 秒对齐，处理夏令时。
- 开盘后第 60 秒触发，所有数据读完后再次检查时间；到第 80 秒仍未完成就跳过。
- 开盘价只读 `crypto-price` 的 `fiveminute.openPrice`，明确传入 `twapEnabled=true`、`twapLookbackSeconds=60`；Gamma 的 BTC/5m 配置也必须明确启用 60 秒 TWAP。当前价只接受 `crypto_prices_chainlink` 的 `btc/usd`。
- 当前价的源时间与接收时间均需在 5 秒内。涨生成 Up，跌生成 Down，持平跳过。
- Gamma 必须给出唯一、活跃、接单中的对应 BTC5m 市场；周期结束时间、Up/Down token 和 slug 必须匹配。
- 每轮先持久记录占用，再读取网络；失败不在同轮重试。重启不恢复旧草稿，启动时已过第 60 秒则等下一轮。
- 草稿的原始价格样本超过 5 秒就作废，最迟开盘后第 80 秒作废。实际可准备时间通常只有约 5 秒。
- `STOP` 立即撤销现有草稿并禁止新草稿；移除 STOP 不会恢复已占用轮次。
- Polymarket 地域检查标明接口来源，明确 `blocked=false` 是必要条件；它本身不能证明 Future 金额准备资格。[官方接口](https://docs.polymarket.com/api-reference/geoblock)
- Future 金额准备资格独立记录为 `future_eligibility`。官方执行路由和适用资格源尚未核实，生产代码固定返回 `UNKNOWN`，因此不会生成金额草稿；没有环境变量、配置、命令行或手动确认可放行。官方资格源接入完成前，不能以登录状态、买入按钮或 Polymarket 允许结果替代它。每次读取状态会重新检查，资格未知时撤销旧草稿。
- 扩展仅在对应轮次的中文页面、唯一可见美元金额框、市价买入票据中填入 1；卖出、限价、打开订单类型菜单、旧轮次、失联或过期均拒绝。

不增加原策略没有的价格过滤。该策略在原文的 5 分钟历史回测中扣费后平均每注 −1.78%，辅助桥不改变这个结论。它没有账户成交、持仓或结算账本，信号与草稿不能用作交易成功证据。

## 安装与使用

工作目录：`/Users/henry/projects/polyhermes`。

独立 Python 环境已创建并安装了两个依赖，不改现有交易 Bridge 环境。若换机器：

```bash
cd /Users/henry/projects/polyhermes
python3 -m venv scripts/future-btc5m-runtime/.venv
scripts/future-btc5m-runtime/.venv/bin/python -m pip install -r scripts/requirements-future-btc5m.txt
```

`python-socks` 用于支持当前系统配置的 SOCKS 连接，依照 [websockets 官方代理文档](https://websockets.readthedocs.io/en/16.0/topics/proxies.html)。外部请求继承既有出口，代码不会切换或禁用代理。

Chrome 登录会话和 Python 的公开行情连接相互独立。当前 Python 3.14 默认 CA 库为空，助手在这种情况下补载已有的 `/etc/ssl/cert.pem`，保留证书和主机名校验。旧 RTDS 的 `filters` 字符串使用紧凑 JSON `{"symbol":"btc/usd"}`；同出口对照测试中，带空格版本只返回快照，紧凑版本持续返回正确的 Chainlink BTC 更新。收到合法、新鲜报价后才清除等待价格状态；证书失败与连接超时分别报告。

一次限时的只读检查，不生成交易草稿、不常驻：

```bash
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --once
```

本次修复已启动本地辅助服务，`--status` 实测返回 `feed_status=CURRENT`。以后服务退出时，在终端运行并保持终端打开：

```bash
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --watch
```

扩展读取 `GET /status`，0.2.4 增加 `POST /bridge/preflight`，仅上报白名单内的只读票据检查结果，不发送账户、余额或登录资料。2026-10-11 新增项目控制页及独立 `/bridge/*` 控制/记录接口，见 [Future BTC5m Bridge 控制页面](future-btc5m-bridge.md)。`--watch` 仍不会下单，当前没有交易执行器。`Ctrl+C` 退出服务。

扩展需由用户在 Chrome 加载：

1. 打开 `chrome://extensions`，启用开发者模式。
2. 点击“加载已解压的扩展程序”，选择 `/Users/henry/projects/polyhermes/scripts/future-btc5m-extension`。
3. 扩展仅在 `https://future.news/*` 注入助手；网络权限为 `127.0.0.1`，后台端点固定为 `http://127.0.0.1:8766/status` 和只读预检报告接口。没有 cookies、storage、tabs 或全网站权限。
4. 刷新 Future 页面，左下角显示助手状态。已安装版本更新后，在扩展页对本助手点击“重新加载”，再刷新 Future；本机已核对加载版本为 0.2.3，权限没有新增。
5. 已结束的 BTC5m 页面会自动点击“前往实时市场”，核对当前轮次后自动只读检查金额栏。“检查页面”可手动重复此检查，均不修改表单。面板显示采样轮次、采样时刻与价格来源；错轮、陈旧和过期信号不会显示可用于入场的方向。“前往本轮市场”保留为失败时的手动导航入口。
6. 当前资格依据显示“未核实”，填入按钮保持禁用。完成官方资格源接入和平台 $1 最低要求核对后，才能继续真实金额准备验收：READY 且数据仍新鲜时，点击“填入 $1 草稿”。你手动选择提示的涨/跌方向，核对轮次、金额、费用、平台最低要求和期限后自行买入。不要把助手的 READY 当成成交确认。

查看状态：

```bash
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --status
```

停止生成草稿（服务运行时状态目录已存在）：

```bash
touch /Users/henry/projects/polyhermes/reports/future-btc5m-assistant/STOP
```

状态文件为 `status.json`，去重记录为 `rounds.jsonl`。记录的是轮次处理事实，不是订单或成交。每次 API 读取重新检查 STOP、期限与数据时效；离线时不会回放磁盘草稿。再次使用前由用户删除 STOP，再从新轮次开始。

## 当前验证与限制

- 68 项测试通过：33 项 Python 行为测试、21 项 Chrome 扩展测试、14 项已有策略/监控基线。覆盖周末/DST、数据与市场校验、固定金额、失联、停止、去重、重启、只读 HTTP、系统 CA 回退、紧凑订阅、TWAP 参数和市场配置、旧轮次/陈旧显示、只读页面预检及独立 Future 资格守卫，以及自动换轮去重、错误按钮拒绝、旧检查清空、SPA URL 先切换而旧 DOM 尚未更新。错误价格口径、旧方向显示、Polymarket 允许结果误当 Future 资格和 SPA 旧票据误报均由失败回归复现，修复后通过。肯定资格的金额流程仅在隔离测试中使用 mock，不能当作生产资格证据。
- 0.2.3 已在已登录 Chrome 实测自动导航：刷新已结束的 1791706200 后，由扩展自动进入 1791706500（北京时间 16:15–16:20）；随后无需浏览器输入，自然换轮时自动进入 1791706800（16:20–16:25）。两轮均核对 URL 与标题，自动只读金额栏检查通过、检查时金额 $1。没有人工代点实时市场、金额写入、方向或买入。记录见 [navigation-verification-20261011.json](../reports/future-btc5m-assistant/navigation-verification-20261011.json)。
- 本地 Chrome 只读检查确认 Future 已登录，订单栏显示“金额 ($)”、输入 1；没有点击买入或检查真实成交。
- CLI 与用户 Chrome 对同一公开地域接口均返回 `blocked=true`；Chrome 请求出口被识别为 US/CA。该接口检查请求 IP，[适用语境为 Polymarket 订单](https://docs.polymarket.com/api-reference/geoblock)，不能据此推断 Future 账户状态。已找到 [Future 官方隐私政策](https://future.news/static/privacypolicy.html)，但它没有明确订单路由、受限地区或资格接口；官网“Odds via Polymarket”也仅证明赔率来源。Future 的具体交易路由与账户资格仍缺少官方依据，保留拦截。
- 已修复实时连接：默认 CA 数量 0，补载系统证书后为 128；保留 `CERT_REQUIRED`、主机名校验与原代理。修复后的 `--once` 返回 `feed_status=CURRENT`、`feed_reason=null`；因探测时超过入场窗口，正确返回 `ENTRY_WINDOW_MISSED`，没有生成信号或草稿。
- 直接运行修复后的接收代码，约 7.7 秒收到 6 个不同源时间的 `crypto_prices_chainlink` / `btc/usd` 报价，源时间年龄为 1.3–2.2 秒。安全诊断记录见 [diagnostics-20261011.json](../reports/future-btc5m-assistant/diagnostics-20261011.json)。这证明当前实时行情连接与新鲜度校验恢复，尚未证明完整的入场及真实页面操作流程。
- 用户已将扩展加载到 Chrome，首次现场预检使用 0.2.1；真实页面收到 `OBSERVING / GEOBLOCK_BLOCKED`，金额按钮保持禁用，`draft=null`。点击只读“检查页面”，未结束市场实测通过，识别唯一中文美元市价买入栏和金额 1；已结束市场因最终按钮显示“价格不可用”而正确拒绝。**尚未实测金额写入操作**，没有点击方向或买入。
- 同轮 `btc-updown-5m-1791652500` 的旧请求开盘价为 82981.98681761073，遗漏 TWAP 参数导致与网页目标 82980.01 不一致，并把该采样方向反转。官方页面查询参数及同出口 API 对照已确认原因；明确启用 60 秒 TWAP 后返回 82980.01481629249，与网页一致。证据见 [reference-price-review.json](../reports/future-btc5m-assistant/reference-price-review.json)。
- 新服务自然处理后续两轮：1791653100 的开盘价 82964.52189404255，对应 Future 目标 82964.52；1791653400 的开盘价 82976.2971943462，对应 Future 图表目标 82976.30。新版面板实测在错页、采样陈旧及入场窗口过期时明确拒用方向。只读端到端记录见 [browser-verification-20261011.json](../reports/future-btc5m-assistant/browser-verification-20261011.json)。
- 0.2.2 与新服务在自然轮次 1791654000 实测一致：`feed_status=CURRENT`、Polymarket `blocked=true`、Future 金额准备资格 `UNKNOWN`、`draft=null`。真实面板显示“Future 金额准备依据：未核实”，金额准备按钮禁用，独立只读金额栏检查仍通过。修复及额外验收记录见 [eligibility-guard-review.json](../reports/future-btc5m-assistant/eligibility-guard-review.json)。
- 公开 Gamma 与两侧 CLOB 订单簿均核对该 BTC5m 市场最低订单量为 5 股；官方市场单说明也要求遵守订单簿的最低量。[官方订单说明](https://docs.polymarket.com/trading/place-orders) 若直接适用此 CLOB 规则，$1 在均价高于 $0.20 时不足 5 股；这是数量推算，不能证明 Future 自己的 $1 执行规则。是否可按 $1 成交仍需其正式规则或平台记录，不能自动加额解决。
- 本地辅助服务已启动，监听 `127.0.0.1:8766`，状态接口确认实时行情为 `CURRENT`、连接错误为空。没有提交代码或部署服务器。现有 Bridge、数据库、配置与未提交工作保持原状。

旧 RTDS 价格流已被官方标为迁移对象，新 PolyBolt 参考价订阅需要账户凭据。本实现沿用原文的公开旧流，失效则显示不可用，不自动获取凭据或换用 Binance 价格。[官方迁移说明](https://docs.polymarket.com/migrate/rtds-to-polybolt)

验证命令：

```bash
scripts/future-btc5m-runtime/.venv/bin/python -m unittest scripts/test_future_btc5m_assistant.py scripts/test_jev_shadow_monitor.py -q
node --test scripts/test_future_btc5m_extension.mjs /Users/henry/projects/binance/test/polymarket-updown.test.mjs
```
