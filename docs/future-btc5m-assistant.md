# Future BTC 5 分钟辅助桥：固定 $1，准备后自动买入

日期：2026-10-11（北京时间）。行情和时窗基于 [周末 BTC 顺势策略](weekend-btc-updown-momentum-strategy.md)；当前票据方向按用户明确的新规则，选择 Future 涨/跌按钮上数字较大的一方。

`2030a89` 已修复并部署按钮选边流程，扩展 0.3.1，284 项相关回归通过。真实轮次 `1791727200` 在 Up 30¢ / Down 71¢ 时，从初始 Up、空金额自动改为 Down / $1，账本记录 READY；未点击最终买入，测试后开关关闭。详见 [修复验收](future-btc5m-bridge.md#按钮较大方向修复验收2030a89) 及 [现场证据](../reports/future-btc5m-assistant/quote-direction-verification-20261011.json)。

## 实现范围

用户已确认“每次 1 元”指 Future 的美元金额 1。助手固定订单本金为 **$1**，没有金额放大、人民币换算、倍投或自动补单。官方订单说明将 BUY 金额定义为美元本金，费用可能额外收取；最终扣款与最低订单要求以 Future 页面为准。[Polymarket 订单说明](https://docs.polymarket.com/trading/place-orders)

实现由独立 Python 信号服务和 Chrome 扩展组成。扩展使用用户已登录的 Future 标签页，不读取 Cookie、私钥或登录令牌，不复制浏览器 profile。Python 服务不引用现有 Bridge，不连接项目数据库，仅监听 `127.0.0.1:8766`。

```mermaid
flowchart LR
  A[公开 Gamma / TWAP 开盘价 / Chainlink] --> B[本地信号服务]
  B --> C[Future 页面辅助扩展]
  C --> N[旧 BTC5m 轮次结束后自动前往实时市场]
  N --> P[核对当前 URL 并只读检查金额栏]
  P --> D[项目开启自动准备票据]
  D --> E[原子认领本轮任务]
  E --> F[比较涨/跌按钮数字，准备较大方向与 $1 并回读]
  F --> G[扩展自动点击一次 Future 买入]
```

用户最初选择“自动准备票据，我最终买入”，0.4.0 起改为准备后自动买入。扩展 0.3.1 起使用独立 `PREPARE_ONLY`：在项目开启开关后认领本轮唯一任务，核对票据内独立 `type="button"` 方向选项，比较两个方向按钮的数字，选择较大的一方并准备固定 $1，再核对实际选中方向。准备步骤本身不点击最终买入；0.4.0 起，同一开关开启时由扩展在 READY 后自动点击一次买入，见 [自动买入](future-btc5m-buy-once.md)。没有服务器交易提交、钱包签名或 Live 执行器；准备记录与订单事实分开，完整步骤见 [Bridge 页面](future-btc5m-bridge.md#自动准备与自动买入)。

以下 `future_eligibility` 与 `/draft` 条件属于旧金额草稿路径，保持原有拦截。新准备路径明确采用用户授权 `USER_REQUEST`，不会制造官方资格证据。

### 自动换轮步骤

1. 每秒读取本地状态，只在 `ASSIST_ONLY`、固定 $1、服务时间与本机相差不超过 3 秒、服务轮次等于当前 UTC 300 秒轮次时工作。STOP、离线、陈旧状态或其它资产/周期页面会暂停。
2. 只有已结束的 Future BTC5m 页面才点击唯一可见、未禁用、文本精确为“前往实时市场”的按钮。当前轮次不点击；未找到按钮则等待页面更新，不使用其它交易控件作为替代。
3. 点击前在当前标签页的自有 sessionStorage key `polyhermes.future-btc5m.navigation` 记录目标。每个目标轮次最多尝试一次，跨页面重新加载仍去重；10 秒未到达则提示手动检查“前往本轮市场”。不读取其它存储键或登录信息。
4. 到达当前轮次 URL，且旧的实时市场按钮已消失后，自动只读检查金额栏；同一个票据容器的英文市场标题必须匹配本轮的美东日期和五分钟范围。URL 切换或旧轮结束时清除之前的检查；页面尚未渲染完成则等待，不把旧票据当作新轮通过。
5. 换页仅浏览公开市场，因此不依赖旧草稿金额准备资格；它不会放行旧金额守卫。`GEOBLOCK_BLOCKED` 或 Future 资格 `UNKNOWN` 时仍可换页，但旧“填入 $1 草稿”按钮保持禁用。0.3.1 的自动准备路径另由项目开关与 `USER_REQUEST` 授权控制。面板分别显示换轮结果、页面检查和信号/资格状态。

## 策略与拒绝条件

- 仅美东周六/周日开盘的 BTC 5 分钟轮次，按 UTC 300 秒对齐，处理夏令时。
- 开盘后第 60 秒触发，所有数据读完后再次检查时间；到第 80 秒仍未完成就跳过。
- 开盘价只读 `crypto-price` 的 `fiveminute.openPrice`，明确传入 `twapEnabled=true`、`twapLookbackSeconds=60`；Gamma 的 BTC/5m 配置也必须明确启用 60 秒 TWAP。当前价只接受 `crypto_prices_chainlink` 的 `btc/usd`。
- 当前价的源时间与接收时间均需在 5 秒内。Chainlink 相对开盘价的 Up/Down/持平只作为参考信息；自动票据方向由当前 Future 两按钮的数字决定，BTC 价格持平也不会替代按钮比较。
- 只解析已绑定本轮票据内的唯一涨/跌方向按钮，接受 0–100 的 `¢` 或 `%` 数值，不要求两侧之和为 100。数字相同、缺失、超出范围或控件歧义均暂停，没有默认 Up 回退。
- schema2 准备记录冻结两按钮快照、较大方向和本机接收快照时间 `quoteObservedAt`；它不是交易所报价更新时间。原始快照超过 5 秒即作废，每个动作还要重新比较页面当前按钮，较大侧改变时失败且不重试本轮。
- Gamma 必须给出唯一、活跃、接单中的对应 BTC5m 市场；周期结束时间、Up/Down token 和 slug 必须匹配。
- 每轮先持久记录占用，再读取网络；失败不在同轮重试。重启不恢复旧草稿，启动时已过第 60 秒则等下一轮。
- 草稿的原始价格样本超过 5 秒就作废，最迟开盘后第 80 秒作废。实际可准备时间通常只有约 5 秒。
- `STOP` 立即撤销现有草稿并禁止新草稿；移除 STOP 不会恢复已占用轮次。
- Polymarket 地域检查标明接口来源，明确 `blocked=false` 是必要条件；它本身不能证明 Future 金额准备资格。[官方接口](https://docs.polymarket.com/api-reference/geoblock)
- Future 金额准备资格独立记录为 `future_eligibility`。官方执行路由和适用资格源尚未核实，生产代码固定返回 `UNKNOWN`，因此不会生成金额草稿；没有环境变量、配置、命令行或手动确认可放行。官方资格源接入完成前，不能以登录状态、买入按钮或 Polymarket 允许结果替代它。每次读取状态会重新检查，资格未知时撤销旧草稿。
- 扩展仅在对应轮次的中文页面、唯一可见美元金额框、市价买入票据中填入 1；卖出、限价、打开订单类型菜单、旧轮次、失联或过期均拒绝。

原文的回测按 BTC 价格方向选择，并未验证当前“按钮数字较大者”的用户规则，不能将原回测结果当作当前方向规则的业绩。它没有账户成交、持仓或结算账本，信号与草稿不能用作交易成功证据。

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

历史行情连接修复已启动本地辅助服务，`--status` 当时实测返回 `feed_status=CURRENT`。以后服务退出时，在终端运行并保持终端打开：

```bash
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --watch
```

扩展读取 `GET /status`，只读报告使用 `POST /bridge/preflight`；0.3.0 新增本机 `/bridge/preparation` 的读取、唯一认领和准备回执。0.6.6 的只读报告增加当前 Future 页面的钱包地址和显示现金，供项目页面展示资产；仍不读取或发送 Cookie、私钥、登录令牌及其它页面数据。项目控制页与准备/订单事实见 [Future BTC5m Bridge 控制页面](future-btc5m-bridge.md)，资产口径与更新步骤见 [我的资产](future-btc5m-assets.md)。`--watch` 不提交买入，`Ctrl+C` 退出服务并要求下次从新轮次开始。

扩展需由用户在 Chrome 加载：

1. 打开 `chrome://extensions`，启用开发者模式。
2. 点击“加载已解压的扩展程序”，选择 `/Users/henry/projects/polyhermes/scripts/future-btc5m-extension`。
3. 扩展仅在 `https://future.news/*` 注入助手；网络权限为 `127.0.0.1`，后台端点固定为本机状态、只读预检与准备接口。没有 cookies、storage、tabs 或全网站权限。
4. 刷新 Future 页面，左下角显示助手状态。已安装版本更新后，在扩展页对本助手点击“重新加载”，再刷新 Future；当前版本为 0.4.1，权限没有新增。
5. 已结束的 BTC5m 页面会自动点击“前往实时市场”，核对当前轮次后自动只读检查金额栏。“检查页面”可手动重复此检查，均不修改表单。面板显示采样轮次、采样时刻与价格来源；错轮、陈旧和过期信号不会显示可用于入场的方向。“前往本轮市场”保留为失败时的手动导航入口。
6. 登录项目，从“Future BTC 5 分钟”打开“自动准备票据开关”。保持 Mac 助手、私有隧道和当前 Future 标签页运行；新鲜本轮采样到来时自动选择按钮数字较大的一方并填写 $1，页面分别报告准备状态及只读预检。旧“填入 $1 草稿”按钮仍因资格未核实禁用。开关开启时，扩展在本轮新票据 READY 后自动点击一次“买入 涨/跌”，面板“自动买入”一行显示监控状态与最近一次点击；点击不表示成交，请在 Future 订单中核对。关闭开关即停止自动买入。

0.3.2 明确显示自动准备的 60–80 秒窗口、关闭或暂停的原因，以及本轮两边按钮报价、较大方向和实际选中方向。报价观察本身不表示已准备；开关关闭时不切换方向或填写金额，超过窗口等待下一轮。行情过期、同价或较大方向改变时仍停止准备；失败轮次不重试。

0.4.0 随扩展加载 `buy_once.js`，跟随“自动准备票据”开关自动买入：开关开启即预先监控，只接受监控开始后新生成的 READY，每轮最多点击一次；开启时本轮票据已生成则从下一轮开始。开关关闭或准备状态无效时不点击。详见 [自动买入](future-btc5m-buy-once.md)。

0.4.1 为每次点击和对 READY 的拒绝写入本机审计账本 `buy_attempts.jsonl`，并提供每轮回测导出；需同时重启助手并重新加载扩展。详见 [审计与回测](future-btc5m-buy-once.md#审计与回测)。

查看状态：

```bash
scripts/future-btc5m-runtime/.venv/bin/python scripts/future_btc5m_assistant.py --status
```

停止生成草稿（服务运行时状态目录已存在）：

```bash
touch /Users/henry/projects/polyhermes/reports/future-btc5m-assistant/STOP
```

状态文件为 `status.json`，去重记录为 `rounds.jsonl`。记录的是轮次处理事实，不是订单或成交。每次 API 读取重新检查 STOP、期限与数据时效；离线时不会回放磁盘草稿。再次使用前由用户删除 STOP，再从新轮次开始。

## 历史准备模式验证：faf15ae

- 历史扩展 0.3.0，`faf15ae` 的 243 项测试通过：146 Python、70 Node、27 Kotlin；前端构建、TypeScript 检查及定向 ESLint 通过。覆盖唯一认领、实际方向与 $1 回读、原始采样 5 秒时效、每步重新核对、撤销/过期/回执未知、准备与预检账本故障、历史报告和当前许可分离。
- 后端与前端静态资源均已由清洁提交 `faf15ae` 构建并部署，app 健康；专用 relay 与 app 网络命名空间及原 Bridge、MySQL、配置等受保护状态核对通过。
- 真实已登录 Chrome 在自然轮次 `1791717900` 自动换轮并完成准备。初始票据金额为空、方向 Up、买入按钮禁用；扩展按 Up 信号准备票据并把空金额写为 1。原生页面回读确认金额 1、Buy Up。账本分别记录 `PENDING=1791717961.447219`、`CLAIMED=1791717961.482274`、`READY=1791717961.53556`（开盘后 61.536 秒）；回执 `checkedAt=1791717961.533`，市场 `https://future.news/zh/event/btc-updown-5m-1791717900`，`amountUsd=1`、`selectedSide=Up`、`noSubmission=true`。
- 生产页面正确显示历史准备 Up / $1，超过 +80 秒后当前准备过期，不把历史 READY 当作当前许可。验收后已关闭开关，`1791718029.897` 确认 `requestedEnabled=false`、`preparation.state=DISABLED`、`effectiveEnabled=false`、全部真实订单统计为 0。最终 Buy 未测试、未点击，自动提交不在当前范围；最终买入仍由用户完成。证据见 [自动准备现场验收记录](../reports/future-btc5m-assistant/preparation-verification-20261011.json)。

## 历史只读验收与限制

以下为自动准备模式上线前的历史记录，不能代替当前方向选择与金额写入验收。

- 历史只读阶段 172 项测试通过：100 Python、52 Node、20 Kotlin；当时前端构建、定向 ESLint 和 TypeScript 检查通过。68 项是更早行情/导航阶段的测试汇总：33 项 Python 行为测试、21 项 Chrome 扩展测试、14 项已有策略/监控基线。覆盖周末/DST、数据与市场校验、固定金额、失联、停止、去重、重启、只读 HTTP、系统 CA 回退、紧凑订阅、TWAP 参数和市场配置、旧轮次/陈旧显示、只读页面预检及独立 Future 资格守卫，以及自动换轮去重、错误按钮拒绝、旧检查清空、SPA URL 先切换而旧 DOM 尚未更新。错误价格口径、旧方向显示、Polymarket 允许结果误当 Future 资格和 SPA 旧票据误报均由失败回归复现，修复后通过。肯定资格的金额流程仅在隔离测试中使用 mock，不能当作生产资格证据。
- 历史扩展 0.2.4 在真实自然轮次 `1791709800`、`1791709861.343` 时只读预检返回 `READ_ONLY_READY`：方向 Up、页面现有金额 $1、`noSubmission=true`。轮次 `1791711900` 在开盘后 61.391 秒再次通过，记录当时显示在生产页面。持续 SPA 页面报告问题已由 `b6e9b90` 修复。该阶段导航和现有票据检查已通过；没有写入金额、选择方向或提交订单，交易执行器仍未连接。
- 0.2.3 已在已登录 Chrome 实测自动导航：刷新已结束的 1791706200 后，由扩展自动进入 1791706500（北京时间 16:15–16:20）；随后无需浏览器输入，自然换轮时自动进入 1791706800（16:20–16:25）。两轮均核对 URL 与标题，自动只读金额栏检查通过、检查时金额 $1。没有人工代点实时市场、金额写入、方向或买入。记录见 [navigation-verification-20261011.json](../reports/future-btc5m-assistant/navigation-verification-20261011.json)。
- 本地 Chrome 只读检查确认 Future 已登录，订单栏显示“金额 ($)”、输入 1；没有点击买入或检查真实成交。
- CLI 与用户 Chrome 对同一公开地域接口均返回 `blocked=true`；Chrome 请求出口被识别为 US/CA。该接口检查请求 IP，[适用语境为 Polymarket 订单](https://docs.polymarket.com/api-reference/geoblock)，不能据此推断 Future 账户状态。已找到 [Future 官方隐私政策](https://future.news/static/privacypolicy.html)，但它没有明确订单路由、受限地区或资格接口；官网“Odds via Polymarket”也仅证明赔率来源。Future 的具体交易路由与账户资格仍缺少官方依据，保留拦截。
- 已修复实时连接：默认 CA 数量 0，补载系统证书后为 128；保留 `CERT_REQUIRED`、主机名校验与原代理。修复后的 `--once` 返回 `feed_status=CURRENT`、`feed_reason=null`；因探测时超过入场窗口，正确返回 `ENTRY_WINDOW_MISSED`，没有生成信号或草稿。
- 直接运行修复后的接收代码，约 7.7 秒收到 6 个不同源时间的 `crypto_prices_chainlink` / `btc/usd` 报价，源时间年龄为 1.3–2.2 秒。安全诊断记录见 [diagnostics-20261011.json](../reports/future-btc5m-assistant/diagnostics-20261011.json)。这是历史行情连接与新鲜度校验恢复证据；后续自然轮次完成上述只读预检，该阶段尚未验收金额写入或交易提交。
- 用户已将扩展加载到 Chrome，首次现场预检使用 0.2.1；真实页面收到 `OBSERVING / GEOBLOCK_BLOCKED`，金额按钮保持禁用，`draft=null`。点击只读“检查页面”，未结束市场实测通过，识别唯一中文美元市价买入栏和金额 1；已结束市场因最终按钮显示“价格不可用”而正确拒绝。**当时尚未实测金额写入操作**，没有点击方向或买入。
- 同轮 `btc-updown-5m-1791652500` 的旧请求开盘价为 82981.98681761073，遗漏 TWAP 参数导致与网页目标 82980.01 不一致，并把该采样方向反转。官方页面查询参数及同出口 API 对照已确认原因；明确启用 60 秒 TWAP 后返回 82980.01481629249，与网页一致。证据见 [reference-price-review.json](../reports/future-btc5m-assistant/reference-price-review.json)。
- 新服务自然处理后续两轮：1791653100 的开盘价 82964.52189404255，对应 Future 目标 82964.52；1791653400 的开盘价 82976.2971943462，对应 Future 图表目标 82976.30。新版面板实测在错页、采样陈旧及入场窗口过期时明确拒用方向。只读端到端记录见 [browser-verification-20261011.json](../reports/future-btc5m-assistant/browser-verification-20261011.json)。
- 0.2.2 与新服务在自然轮次 1791654000 实测一致：`feed_status=CURRENT`、Polymarket `blocked=true`、Future 金额准备资格 `UNKNOWN`、`draft=null`。真实面板显示“Future 金额准备依据：未核实”，金额准备按钮禁用，独立只读金额栏检查仍通过。修复及额外验收记录见 [eligibility-guard-review.json](../reports/future-btc5m-assistant/eligibility-guard-review.json)。
- 公开 Gamma 与两侧 CLOB 订单簿均核对该 BTC5m 市场最低订单量为 5 股；官方市场单说明也要求遵守订单簿的最低量。[官方订单说明](https://docs.polymarket.com/trading/place-orders) 若直接适用此 CLOB 规则，$1 在均价高于 $0.20 时不足 5 股；这是数量推算，不能证明 Future 自己的 $1 执行规则。是否可按 $1 成交仍需其正式规则或平台记录，不能自动加额解决。
- 历史生产只读阶段，本地辅助服务监听 `127.0.0.1:8766`。后端与前端 `d5464c0`、ServiceWorker 导航缓存修复 `83c2e12`、专用 relay 超时修复 `d4c6862` 当时已上线；app 健康，原 Bridge、MySQL 与配置未改。正式 Chrome 页面的鉴权、关闭控制、断线未知提示、恢复后新鲜报告与现有 $1 票据、历史通过记录和空订单列表已验收；relay 连续 40 次查询全部成功。详见 [生产只读验收记录](../reports/future-btc5m-assistant/production-preorder-verification-20261011.json)。Mac 助手与前台 SSH 隧道须保持运行；标签页休眠或报告过期仍会拒绝当前就绪。该阶段没有验证金额写入或交易提交。

旧 RTDS 价格流已被官方标为迁移对象，新 PolyBolt 参考价订阅需要账户凭据。本实现沿用原文的公开旧流，失效则显示不可用，不自动获取凭据或换用 Binance 价格。[官方迁移说明](https://docs.polymarket.com/migrate/rtds-to-polybolt)

历史行情/导航基线验证命令（当前完整测试汇总见上文）：

```bash
scripts/future-btc5m-runtime/.venv/bin/python -m unittest scripts/test_future_btc5m_assistant.py scripts/test_jev_shadow_monitor.py -q
node --test scripts/test_future_btc5m_extension.mjs /Users/henry/projects/binance/test/polymarket-updown.test.mjs
```
