# Bridge 交易可靠性提升

## 需求

### REQ-1: 网络/代币模态框主动处理

当 Polymtrade 在 outcome 点击后弹出“选择网络和代币”模态框时，Bridge 应尝试主动选择 Polygon 网络和 USDC 代币，而不是仅关闭模态框。若找不到首选项，再回退到关闭。

### REQ-2: BUY 前余额检查

在执行 BUY 前，Bridge 应尝试从页面读取 USDC/pUSD 余额。若可读取余额且明显低于下单金额（含 5% 缓冲），应快速失败并返回清晰错误，避免进入反复弹窗循环。

### REQ-3: BUY 后成交校验

BUY 提交后，Bridge 应尝试通过 portfolio 或余额变化间接验证订单是否生效。验证不通过时不得将交易标为 SUCCESS，应返回 `verified: false` 供后续审计。

### REQ-4: 失败日志完整

所有捕获异常并记录为警告的路径，必须将异常原因完整写入日志，禁止出现空原因的日志条目。

### REQ-5: 持仓 enrich 避免页面跳转

`fetch_portfolio_positions()` 在 enrich 每个持仓时，不得通过点击 card 触发页面导航；应优先使用 card 中已存在的 `href`/`data-*` 或 Gamma API title search。

### REQ-6: Gamma API 调用带重试

所有从 Bridge 发往 Gamma API（events/markets）的请求必须具备指数退避重试机制，默认至少重试 3 次。

### REQ-7: 持仓 enrich 并发执行

当 enrichment 不再依赖页面点击/导航后，多个持仓的 enrichment 应并发执行，降低 `/portfolio` 接口延迟。

### REQ-8: BUY 后精确成交校验

BUY 提交后，Bridge 应在提交前捕获 USDC 余额与目标 event-page 持仓数量基线；提交后再次读取余额与持仓数量。若余额下降达到下单金额的 50% 以上，或 event-page 持仓数量增加，则视为成交通过；否则仍保留 success indicator 兜底校验。校验结果通过 `verified` 字段返回。

### REQ-9: SELL 路径加固

SELL 执行路径应具备与 BUY 同等级别的鲁棒性：导航后等待事件 URL 与页面内容；主动处理网络/代币模态框；重试打开 SELL 弹窗；检测弹窗是否真正打开；提交前捕获余额与持仓数量基线；提交后通过持仓数量下降、余额增加或 success indicator 校验成交。

### REQ-10: SELL 后校验避免假阴性

SELL 提交后，Bridge 应尝试校验持仓数量下降或余额增加。若 UI 尚未反映变化，不得直接将交易标为 FAILED；应记录为 SUCCESS 并附加 `verified: false` 与审计日志，避免假阴性。

### REQ-11: BUY outcome 选择鲁棒性

BUY 路径在选择 outcome 时应等待页面内容渲染，通过滚动触发懒加载，允许最多 4 次重试，并支持更多 side label 变体（如 Buy Yes/Buy No/Long/Short）。

### REQ-12: BUY 金额输入鲁棒性

BUY 金额输入应支持更广泛的 input selector，限制只选择 dialog/trade 区域内的输入框，并在失败时保存截图以便排查。

### REQ-13: SELL 持仓匹配与数量降级

SELL 前的 live portfolio 匹配应同时比较 `conditionId`、`marketSlug`、`eventSlug` 与市场标题；若实际持仓少于预期，应自动卖出实际可用数量，而不是直接跳过。

### REQ-14: Bridge 可观测性指标

Bridge 应维护内存级指标计数器，涵盖信号接收/过滤/执行、BUY/SELL 成功与失败、Gamma API 请求与失败、模态框阻塞/关闭、Portfolio 请求与错误，并通过 `/metrics` 接口以 JSON 形式暴露。

## 场景

### SC-1: 未设置默认网络时执行 BUY

**Given** Bridge 账户在 Polymtrade 未设置默认网络  
**When** 收到 BUY 信号并点击 outcome  
**Then** 模态框弹出后，Bridge 选择 Polygon + USDC  
**And** 继续填写金额并提交订单  
**And** 不再因同一模态框反复失败

### SC-2: 余额不足时执行 BUY

**Given** Bridge 账户 USDC 余额为 $0.50  
**When** 收到 BUY $2.00 的信号  
**Then** Bridge 在尝试点击 outcome 前快速失败  
**And** 返回错误信息包含当前余额和所需金额  
**And** `bridge_trade_record` 状态为 FAILED

### SC-3: BUY 提交后未检测到账户变化

**Given** BUY 订单已提交  
**When** 15 秒内 portfolio 和余额均未发生变化  
**Then** 交易仍记录为执行过  
**And** 返回结果中 `verified: false`  
**And** 日志记录待审计警告

### SC-4: 异常日志完整

**Given** `_enrich_position` 调用 Gamma API 或页面操作时抛出异常  
**When** 异常被捕获并记录  
**Then** 日志消息包含异常类型和具体原因  
**And** 不出现以冒号结尾但无后续内容的日志

### SC-5: 持仓 enrich 不触发页面导航

**Given** `/portfolio` 页面已加载并包含多个持仓卡片  
**When** Bridge 调用 `fetch_portfolio_positions()`  
**Then** enrichment 优先通过 Gamma markets/events title search 完成  
**And** 不出现 `net::ERR_ABORTED at https://polym.trade/portfolio`  
**And** `/portfolio` 接口返回 200

### SC-6: Gamma API 瞬断时自动重试

**Given** Gamma API 前两次请求超时/连接失败  
**When** Bridge 调用 `_gamma_request_with_retry()`  
**Then** 第 3 次请求成功并返回数据  
**And** 日志记录前两次失败及退避等待时间

### SC-7: BUY 成交后精确校验

**Given** Bridge 已执行 BUY $2.00  
**When** `_capture_buy_baseline()` 在提交前记录余额 $100.00 与持仓数量 0  
**And** 提交后余额变为 $97.90，event-page 持仓数量变为 10  
**Then** `_verify_buy_executed()` 返回 `verified: true`  
**And** 返回结果中包含前后余额与持仓数量供审计

### SC-8: BUY 未成交时精确校验失败

**Given** Bridge 已执行 BUY $2.00  
**When** 提交前后余额均为 $100.00 且 event-page 持仓数量均为 0  
**And** 页面未出现 success indicator  
**Then** `_verify_buy_executed()` 返回 `verified: false`  
**And** 返回结果中标记 `verified: false` 并记录审计日志

### SC-9: SELL 弹窗被模态框阻塞时自动处理

**Given** Bridge 在执行 SELL 时弹出“选择网络和代币”模态框  
**When** `_execute_sell()` 检测到模态框  
**Then** 优先选择 Polygon + USDC  
**And** 继续打开 SELL 弹窗并提交订单  
**And** 不直接返回失败

### SC-10: SELL 提交后 UI 延迟更新

**Given** Bridge 已执行 SELL 10 shares  
**When** 提交后 live portfolio 数量尚未下降  
**And** 8 次轮询（每次 2.5 秒）内仍未下降  
**Then** 交易仍记录为 SUCCESS  
**And** 返回结果中 `verified` 由 `_verify_sell_executed()` 决定  
**And** 日志记录审计警告

### SC-11: BUY outcome 行懒加载导致首次选择失败

**Given** 事件页面 outcome 行尚未完全渲染  
**When** `_select_polymtrade_outcome()` 首次未找到目标行  
**Then** 自动滚动页面触发懒加载  
**And** 最多重试 4 次后成功点击目标 side 按钮

### SC-12: SELL 预期持仓大于实际持仓

**Given** Bridge 预期卖出 10 shares  
**When** live portfolio 实际只有 6 shares  
**Then** 自动调整卖出数量为 6 shares  
**And** 交易继续执行而不是标为 FAILED

### SC-13: Bridge 指标暴露

**Given** Bridge 已处理若干信号并遇到一次 Gamma API 失败  
**When** 调用 `/metrics` 接口  
**Then** 返回的 JSON 中 `signals_received`、`trades_buy_total`、`gamma_api_failures` 等计数正确反映运行状态

### REQ-15: BUY 不依赖 eventId 出现在 URL

BUY 执行路径不得将 `eventId` 出现在浏览器 URL 作为硬门槛。当 Bridge 账户在目标事件上无持仓、portfolio 轮播离开目标事件时，Bridge 应通过页面内容（目标市场关键词、Yes/No 按钮、outcome 文本）确认当前页面是否已渲染目标市场；若未渲染，应重新导航到目标事件 URL（含 `eventSlug` 兜底 URL）并重试。

### SC-14: 无持仓事件的 BUY 因轮播被误判失败

**Given** Bridge 账户在哥伦比亚大选事件（eventId=34584）上无持仓，但在其他事件上有持仓  
**When** 收到该事件 BUY Yes $2.00 的信号  
**Then** `_execute_buy()` 导航到目标事件页面  
**And** 即使 portfolio 轮播使 URL 不再包含 `34584`，仍能通过内容可见性检查确认目标市场已渲染  
**And** 成功选择 outcome 并提交订单  
**And** 不再抛出 `Target event 34584 URL never appeared`

### REQ-16: 政治候选型市场 outcome 选择不得被泛词干扰

对于政治候选型市场，Bridge 应以候选人/实体名称作为主要行锚点，避免 `presidential`、`election`、`candidate` 等通用政治词汇主导匹配。静态回归测试必须覆盖 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?` 这类候选行。

### SC-15: 哥伦比亚总统候选人市场选择 Abelardo 行

**Given** Polymtrade 页面展示多个哥伦比亚总统候选人行  
**When** 收到 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?` 的 BUY Yes 信号  
**Then** `_extract_market_keywords()` 返回候选人相关关键词，如 `abelardo`、`espriella`、`colombian`  
**And** `_select_polymtrade_outcome()` 点击 `Abelardo de la Espriella` 行内的 Yes 按钮  
**And** 不点击其他候选人行或页面上的通用 Yes/No 按钮

### REQ-17: Bridge 审计必须输出失败分类与下一步候选

Bridge 的只读审计工具和 `/audit` 接口必须对近期 `FAILED` 记录按错误原因聚类，输出稳定的 `failure_buckets`、每类样本记录、actionability、next action 建议，以及按代码修复优先级排序的 `next_action_candidates`。账户余额、真实仓位不足、充值/网络默认设置等状态类失败不得排在 selector/navigation 代码类失败前面。

### SC-16: 失败记录聚类生成下一步修复队列

**Given** `bridge_trade_record` 中存在 `Could not select outcome`、`Could not enter trade amount`、`Could not click sell button`、`Network/deposit modal keeps blocking the trade` 等 FAILED 记录  
**When** 调用 `bridge_reliability_audit.py` 或 Bridge `/audit` 接口  
**Then** 返回 `failure_buckets`，其中每个 bucket 包含 `bucket`、`count`、`actionability`、`next_action`、`sample_record_ids`  
**And** 返回 `next_action_candidates`，优先包含 selector/navigation 代码类 bucket  
**And** `Network/deposit modal keeps blocking the trade` 这类账户状态/模态框边界问题不会压过 `select_outcome`、`amount_input`、`click_submit` 等代码修复候选

### REQ-18: 电竞队伍型市场选择必须忽略事件泛词

Bridge 在选择电竞队伍型 categorical market outcome 时，必须优先使用队伍的独特名称片段作为行锚点，并忽略 `team`、赛事名、比赛等级等事件泛词，避免在多个队伍都包含 `Team` 或页面标题包含赛事名时选错行或找不到行。

### SC-17: Team Spirit 市场点击正确队伍行

**Given** Polymtrade 页面展示 `Team Vitality`、`Team Spirit`、`G2 Esports` 等多个电竞队伍行  
**When** 收到 `Will Team Spirit win IEM Cologne Major 2026?` 的 BUY Yes 信号  
**Then** `_extract_market_keywords()` 返回 `spirit` 作为主要行锚点，并过滤 `team`、`iem`、`cologne`、`major`  
**And** `_select_polymtrade_outcome()` 点击 `Team Spirit` 行内的 Yes 按钮  
**And** 不点击 `Team Vitality`、`G2 Esports` 或事件标题区域的按钮

### REQ-19: BUY 金额输入必须支持自定义可编辑控件

Bridge 在 BUY 打开交易面板后，不得只依赖传统 `<input>` 金额框。金额输入检测与填充必须支持 `textarea`、`role=textbox`、`contenteditable=true`、`contenteditable=plaintext-only` 等 Polymtrade 可能使用的自定义金额控件，并继续排除搜索框、钱包地址、导航栏等噪声输入区域。

### SC-18: Contenteditable 金额框可以完成 BUY 金额填写

**Given** BUY 交易面板渲染一个 `role=textbox` 且 `contenteditable=true` 的金额控件  
**When** Bridge 执行 `_is_buy_dialog_open()` 与 `_enter_amount(2.0)`  
**Then** `_is_buy_dialog_open()` 返回 true  
**And** `_enter_amount()` 能清空并输入 `2.0`  
**And** 不会抛出 `Could not enter trade amount`

### REQ-20: 交易提交按钮必须等待可点击状态并支持自定义按钮

Bridge 在 BUY/SELL 最后提交时，不得只尝试一次传统 `<button>`。提交逻辑必须在短时间窗口内重试，支持 `button`、`role=button`、`input[type=submit]`、`tabindex=0`、`.cursor-pointer` 等交易面板内的自定义确认控件，并跳过 `disabled`、`aria-disabled=true`、`data-disabled=true`、`pointer-events:none`、取消/充值/提现/100% 等非提交按钮。

### SC-19: 延迟启用的自定义确认卖出按钮可被点击

**Given** SELL 交易面板渲染一个 `role=button` 的 `确认卖出` 控件，初始 `aria-disabled=true`，随后报价更新后变为可点击  
**When** Bridge 执行 `_click_sell_button()`  
**Then** Bridge 在短轮询窗口内等待按钮可点击  
**And** 点击该 `确认卖出` 控件  
**And** 不会抛出 `Could not click sell button`

### REQ-21: Bridge 审计必须标记失败样本的回归覆盖状态

Bridge audit 必须为近期 FAILED 记录输出 `coverage_hint`，并在 `failure_buckets` 中统计 `covered_count`、`uncovered_count`、`coverage_ids`、`uncovered_sample_record_ids` 和 `uncovered_sample_markets`。只有 exact fixture 覆盖的历史失败才可计入 covered；partial fixture 只能作为提示，不得把整个 bucket 从下一步候选中移除。

### SC-20: 已 exact 覆盖的历史失败不挤占下一步队列

**Given** 历史 FAILED 记录中同时存在 `Team Spirit` 电竞队伍 outcome 选择失败和未覆盖的 `Uruguay Group H` outcome 选择失败  
**When** 调用 `bridge_reliability_audit.py` 或 Bridge `/audit` 接口  
**Then** `Team Spirit` 记录的 `coverage_hint.covered` 为 true，且 `coverage_id` 为 `esports_team_selector_fixture`  
**And** 对应 bucket 的 `covered_count` 与 `uncovered_count` 分别反映已覆盖和未覆盖样本  
**And** 若某个 code bucket 的所有样本都已 exact 覆盖，该 bucket 不进入 `next_action_candidates`  
**And** partial 覆盖的 `amount_input` 或 `click_submit` 仍保留为可继续跟进的候选

### REQ-22: 世界杯 group 多国家市场必须覆盖中文国家行

Bridge selector 必须能在世界杯 group categorical market 中，用英文标题/slug 提取出的国家关键词匹配 Polymtrade 中文国家行，并点击目标国家行内的对应 Yes/No 按钮。回归覆盖必须包含 Uruguay、Ecuador、Belgium、Spain 这批高频失败国家，并由 audit exact coverage 规则标记。

### SC-21: Uruguay/Ecuador/Belgium/Spain group 行选择与 coverage 标记

**Given** Polymtrade 页面展示 `乌拉圭`、`厄瓜多尔`、`比利时`、`西班牙` 等中文国家行，每行包含 Yes/No 或 是/否 按钮  
**When** Bridge 收到 `Will Uruguay win Group H...`、`Will Ecuador win Group E...`、`Will Belgium win Group G...`、`Will Spain win Group H...` 等 BUY 信号  
**Then** `_extract_market_keywords()` 返回对应中文国家别名  
**And** `_select_polymtrade_outcome()` 点击对应国家行内的目标 side 按钮  
**And** audit 将这些历史 `select_outcome` 失败标记为 `coverage_id=world_cup_group_multi_country_fixture` 的 exact covered 样本

### REQ-23: 剩余世界杯国家市场必须处理重音、多词国家名和对手码污染

Bridge selector 必须覆盖 Haiti、Curaçao、Cape Verde、Scotland、USA 等剩余高频世界杯国家市场。关键词提取必须支持重音归一化、多词国家中文别名，并在标题已明确目标国家时避免从 slug 中扩展非目标对手国家码，例如 `fifwc-bra-hai` 的 Brazil 不得成为 Haiti 市场的强关键词。

### SC-22: Haiti/Curaçao/Cape Verde/Scotland/USA 行选择与 coverage 标记

**Given** Polymtrade 页面展示 `海地`、`库拉索`、`佛得角`、`苏格兰`、`美国` 等中文国家行，每行包含 Yes/No 或 是/否 按钮  
**When** Bridge 收到 `Will Haiti win...`、`Will Curaçao win Group E...`、`Will Cape Verde reach the final...`、`Will Scotland win Group C...`、`Will USA reach the final...` 等 BUY 信号  
**Then** `_extract_market_keywords()` 返回对应中文国家别名  
**And** Haiti 信号不会把 Brazil/巴西 作为目标关键词  
**And** `_select_polymtrade_outcome()` 点击对应国家行内的目标 side 按钮  
**And** audit 将这些历史 `select_outcome` 失败标记为 `coverage_id=world_cup_remaining_country_fixture` 的 exact covered 样本

### REQ-24: 电竞队伍型 outcome 必须以 outcome 自身作为强锚点

当 Polymtrade 市场 outcome 不是 Yes/No，而是 `Vitality`、`Team Falcons`、`G2`、`Spirit` 等队伍名时，Bridge 必须把 outcome 自身提取出的关键词放在 market title/slug 关键词之前，避免赛事标题同时包含两队时锚到错误行。关键词提取必须过滤 `Counter-Strike`、`BO3`、`Map`、`Handicap`、`Playoffs` 等赛事泛词，同时保留 `G2` 这类短 alphanumeric 队名。

### SC-23: Vitality/Falcons/G2/Spirit 电竞行选择与 coverage 标记

**Given** Polymtrade 页面展示 `Vitality`、`Team Falcons`、`G2`、`Spirit` 以及 `Team Falcons +1.5` 等电竞队伍/盘口行  
**When** Bridge 收到 `Counter-Strike: Vitality vs Team Falcons...`、`Map 1 Winner`、`Counter-Strike: Spirit vs G2...`、`Map Handicap...Team Falcons` 等 BUY 信号  
**Then** `_select_polymtrade_outcome()` 优先使用 outcome 自身作为行锚点  
**And** `G2` 不会因 2 字符 token 过滤而丢失  
**And** 点击目标队伍行内的 Yes/是 按钮  
**And** audit 将这些历史 `select_outcome` 失败标记为 `coverage_id=esports_match_team_selector_fixture` 的 exact covered 样本

### REQ-25: Select outcome 剩余世界杯样本必须收尾覆盖

Bridge selector 与 audit coverage 必须覆盖 `Will USA win Group D in the 2026 FIFA World Cup?` 和 `Will Mexico reach the 2026 FIFA World Cup final?` 这两个剩余 `select_outcome` 历史未覆盖样本，使 `select_outcome` bucket 能准确反映当前仍未覆盖的真实问题，而不是历史 fixture 缺口。

### SC-24: USA Group D 与 Mexico final 标记为 exact covered

**Given** Polymtrade 页面展示 `美国` group 行和 `Mexico` final 行，每行包含目标 side 按钮  
**When** Bridge 收到 `Will USA win Group D...` 或 `Will Mexico reach the 2026 FIFA World Cup final?` 的 BUY No 信号  
**Then** `_select_polymtrade_outcome()` 点击目标行内的 No/否 按钮  
**And** audit 将对应历史 `select_outcome` 失败标记为 `coverage_id=world_cup_select_outcome_cleanup_fixture` 的 exact covered 样本

### REQ-26: BUY 金额输入失败必须区分表单未打开与控件未识别

Bridge 在 BUY outcome 点击后必须先确认真实交易表单已打开，再进入金额输入步骤。若页面仍停留在 portfolio 或只出现非交易用途的 `买入 $PM` 按钮，不得继续尝试输入金额；应抛出 `Could not open buy dialog after outcome click`，并由 audit 归类为 `buy_dialog_open`。真实交易金额控件必须支持 `type=text`、`aria-label=USDC`、`role=spinbutton`、`data-test/data-testid` amount 等常见形态。

### SC-25: portfolio 假阳性不再污染 amount_input

**Given** 页面仍是 Polymtrade portfolio，只有钱包区的 `买入 $PM` 按钮和持仓列表  
**When** Bridge 检查 BUY 表单是否打开  
**Then** `_is_buy_dialog_open()` 返回 false  
**And** `_execute_buy_on_page()` 不再继续调用 `_enter_amount()`  
**And** 错误被归类为 `buy_dialog_open`，而不是 `amount_input`

### SC-26: 新型金额控件可输入 USDC 金额

**Given** BUY 交易表单使用 `input type=text aria-label=USDC` 或 `role=spinbutton` 作为金额控件  
**When** Bridge 执行 `_enter_amount(2.0)`  
**Then** Bridge 识别该控件并填入 `2.0`  
**And** 不会抛出 `Could not enter trade amount`

### REQ-27: 目标市场可见性必须支持中文交易动作行

Bridge 在判断目标市场是否已渲染时，不得只依赖全页短 `Yes/No` 按钮。若目标关键词所在的市场行内存在 `买入`、`卖出`、`Buy`、`Sell` 等可交易动作，也必须认定目标市场已经可见，避免候选人/中文界面页面被误判为 `Target market content never appeared`。

### SC-27: Abelardo 中文交易动作行可通过目标可见性检查

**Given** Polymtrade 页面展示 `Abelardo de la Espriella` 候选人行，行内按钮文本为 `买入 99¢` 与 `卖出 1¢`，没有短 `Yes`/`No` 文本  
**When** Bridge 调用 `_is_target_event_visible()` 或 `_wait_for_page_ready()` 检查 `Will Abelardo de la Espriella  win the 2026 Colombian presidential election?`  
**Then** Bridge 通过目标行关键词与交易动作判断该市场可见  
**And** audit 将 Abelardo 的 `target_market_missing` 历史失败标记为 `coverage_id=content_based_event_visibility_fixture` 的 exact covered 样本

### REQ-28: SELL 失败必须拆分弹窗未打开与提交后无效果

Bridge 在执行 SELL 时必须将“无法打开卖出弹窗”和“提交后 live portfolio 持仓未下降”拆分为独立可行动失败类型。若多次点击卖出后仍未检测到真实 SELL 表单，不得继续输入卖出份额；必须保存诊断截图并抛出 `Could not open sell dialog after sell button click`。Audit 必须将 `Could not open sell dialog...` 归类为 `sell_dialog_open`，将 `SELL post-submit verification failed...` 归类为 `sell_post_submit_no_effect`，避免这些 SELL 风险混在 `other` 中。

### SC-28: SELL 弹窗未打开时不继续输入份额

**Given** Bridge 已尝试点击目标持仓的卖出按钮，但 `_is_sell_dialog_open()` 在重试窗口内仍为 false  
**When** `_execute_sell()` 进入卖出份额输入前的安全检查  
**Then** Bridge 保存 `/tmp/trade_sell_dialog_open_error.png`  
**And** 抛出 `Could not open sell dialog after sell button click`  
**And** 不再调用 `_enter_sell_shares()`  
**And** audit 将该错误归类为 `sell_dialog_open`

### SC-29: SELL 提交后无持仓变化进入独立队列

**Given** Bridge 提交 SELL 后 live portfolio 中目标 outcome 数量未下降  
**When** `/audit` 读取 `SELL post-submit verification failed: live portfolio quantity did not decrease...` 失败记录  
**Then** audit 将该记录归类为 `sell_post_submit_no_effect`  
**And** `next_action_candidates` 显示该 bucket 的独立 next action，而不是将其放入 `other`

### REQ-29: Select outcome cleanup 必须覆盖 Germany Group E 与 Argentina final

Bridge selector 与 audit coverage 必须覆盖剩余 `select_outcome` 历史未覆盖样本 `Will Germany win Group E in the 2026 FIFA World Cup?` 和 `Will Argentina reach the 2026 FIFA World Cup final?`，使 `select_outcome` bucket 不再因历史 fixture 缺口进入下一步候选。

### SC-30: Germany Group E 与 Argentina final 标记为 exact covered

**Given** Polymtrade 页面展示 `德国` group 行和 `Argentina` final 行，每行包含目标 side 按钮  
**When** Bridge 收到 Germany Group E 或 Argentina final 的 BUY No 信号  
**Then** `_select_polymtrade_outcome()` 点击目标行内的 No/否 按钮  
**And** audit 将对应历史 `select_outcome` 失败标记为 exact covered  
**And** `/audit` 中 `select_outcome` 的 `uncovered_count` 为 0

### REQ-30: Copy SELL 无 live 持仓必须记录可见 skip

Copy-trading SELL 在进入 Polymtrade UI 前必须检查 live portfolio 中是否存在目标市场/outcome 的真实持仓。若 live quantity 为 0 或更小，系统不得尝试打开卖出弹窗；必须写入 `bridge_trade_record` 的 FAILED 记录，错误为 `Live portfolio insufficient position, skipped (...)`，并继续处理后续信号。

### SC-31: 无 live 持仓不再产生 sell_dialog_open

**Given** position ledger 或历史记录认为某市场可卖出，但 live portfolio 中目标 outcome 数量为 0  
**When** copy-trading SELL 信号进入执行链路  
**Then** Bridge 写入 FAILED skip 记录  
**And** 不调用 `executor.execute_trade(... side="SELL")`  
**And** 不产生 `Could not open sell dialog...sellButtons=0` 这类 UI 失败  
**And** audit 将旧的 Ludvig Aberg `sell_dialog_open` 历史失败标记为 `coverage_id=live_sell_position_precheck`

### REQ-31: Audit 必须降级历史测试或缺元数据记录

Audit 在分类失败时必须使用 row metadata 区分真实交易失败与历史测试/缺元数据记录。`market_title` 缺失的 `select_outcome` 失败，或零金额/零数量的 `*test*` 手工记录，不得继续作为 `select_outcome` code selector 候选。

### SC-32: Mbappe goal test 不挤占 selector 修复队列

**Given** 历史 FAILED 记录标题为 `Mbappe goal test`，金额或数量为 0，错误为 `Could not select outcome`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `test_or_incomplete_record` bucket  
**And** `test_or_incomplete_record` 不进入 `next_action_candidates`  
**And** `/audit` 中真实 `select_outcome` bucket 的 `uncovered_count` 不被该记录增加

### REQ-32: 交易提交按钮必须支持属性型与图标型控件

Bridge 在点击 BUY/SELL 最终提交按钮时，不能只依赖可见文本。提交按钮选择必须同时读取 `aria-label`、`title`、`value`、`data-testid`、`data-test`、`id`、`name` 和 `type` 等属性，并支持 `button type=submit`、`input type=submit`、只有图标但带 `aria-label` 的按钮，以及 `data-testid/data-test/id` 中包含 `submit`、`sell`、`buy` 的控件。

### SC-33: 属性型 SELL submit 可点击

**Given** SELL 确认弹窗中提交按钮没有可见文本，但存在 `type=submit data-testid=sell-submit aria-label=确认卖出`  
**When** Bridge 执行 `_click_sell_button()`  
**Then** Bridge 通过属性评分识别该按钮  
**And** 点击该提交按钮  
**And** 不会抛出 `Could not click sell button`

### SC-34: 图标型 SELL confirm 可点击并保留失败截图

**Given** SELL 确认弹窗中提交按钮只有图标，但按钮带有 `aria-label=确认卖出` 或 `data-test=confirm-sell`  
**When** Bridge 执行 `_click_sell_button()`  
**Then** Bridge 点击该图标型确认按钮  
**And** 若重试窗口内仍无法点击 SELL 提交按钮，Bridge 保存 `/tmp/trade_sell_submit_button_error.png` 后抛出 `Could not click sell button`

### REQ-33: Audit row-level 降级必须覆盖 UI code bucket

Audit 在分类失败时必须对 `select_outcome`、`amount_input`、`buy_dialog_open`、`click_submit`、`target_market_missing`、`target_event_url_missing` 等 UI code bucket 统一应用 row metadata 降级规则。缺少 `market_title` 的记录，或标题包含 `test` 且金额/数量为 0 的手工记录，不得继续作为真实 UI 选择器或输入控件问题进入修复队列。`/audit` 输出的 `failure_bucket`、bucket summary 和 `coverage_ids` 必须使用最终 row-level bucket 重新计算，避免降级后的记录继承原 code bucket 的 fixture coverage。

### SC-35: 缺元数据和零金额 amount_input 不挤占金额输入修复队列

**Given** 历史 FAILED 记录缺少 `market_title` 且错误为 `Could not enter trade amount`  
**And** 另有 `Mbappe goal test` 手工记录金额/数量为 0 且错误为 `Could not enter trade amount`  
**When** 调用 `bridge_reliability_audit.py` 或 Bridge `/audit` 接口  
**Then** 这些记录进入 `test_or_incomplete_record` bucket  
**And** `amount_input` bucket 只统计真实交易金额输入失败  
**And** `test_or_incomplete_record.coverage_ids` 为空，不继承 `custom_amount_input_fixture`  
**And** `test_or_incomplete_record` 不进入 `next_action_candidates`

### REQ-34: BUY 金额输入必须支持中文属性和非原生数字控件

Bridge 在 BUY 表单中寻找金额控件时，必须识别中文 `aria-label`/placeholder/name/id/data-test 中的 `金额`、`数量`，以及 `USDC`、`amount`、`quantity`、`shares` 等英文属性。若交易表单使用非原生 `div role=spinbutton` 或 `role=textbox` 控件，Bridge 必须通过键盘输入或 DOM value/textContent/aria-valuenow 事件兜底写入金额。若金额仍无法输入，Bridge 必须同时保存截图和候选输入控件 DOM 诊断 JSON，方便下一轮 loop 精准修复。

### SC-36: 中文 aria 与自定义 spinbutton 金额控件可写入

**Given** BUY 交易表单使用 `input type=text aria-label="金额 USDC"` 作为金额控件  
**When** Bridge 执行 `_enter_amount(2.0)`  
**Then** 该 input 的 value 被写入 `2.0`  
**And** `_is_buy_dialog_open()` 认定 BUY 表单已打开  
**Given** BUY 交易表单使用 `div role=spinbutton aria-label="金额 USDC"` 作为金额控件  
**When** Bridge 执行 `_enter_amount(2.0)`  
**Then** Bridge 通过键盘或 DOM 事件将该控件的 text/aria-valuenow 写入 `2.0`  
**And** 若金额输入最终失败，Bridge 保存 `/tmp/trade_amount_input_error.png` 与 `/tmp/trade_amount_input_candidates.json`

### REQ-35: 页面跳转竞态必须自动重试

Bridge 在 BUY/SELL 执行链路中进行 DOM `evaluate` 或 `evaluate_handle` 时，必须识别 Polymtrade 页面跳转导致的 transient execution context 丢失，例如 `Execution context was destroyed, most likely because of a navigation`。遇到这类短暂竞态时，Bridge 必须等待页面 `domcontentloaded` 后重试，而不是直接将交易标记为失败。若重试后仍失败或页面已关闭，错误必须保留 `navigation_race` 语义，供 `/audit` 正确分类。

### SC-37: page-ready evaluate 遇到导航竞态后重试成功

**Given** `_wait_for_page_ready()` 第一次调用页面 `evaluate` 时抛出 `Execution context was destroyed, most likely because of a navigation`  
**When** 页面随后完成 `domcontentloaded` 且第二次 `evaluate` 返回目标内容可见  
**Then** `_wait_for_page_ready()` 返回 true  
**And** Bridge 至少等待一次页面 load state  
**And** `/audit` 将 `navigation race persisted` 或 `page closed during navigation retry` 仍归类为 `navigation_race`

### REQ-36: SELL submit 前必须确认仍在交易弹窗上下文

Bridge 在点击 SELL 最终提交按钮前，必须确认真实 SELL 确认弹窗仍然打开。若页面已经回到 portfolio 或只剩持仓列表/钱包区卖出按钮，系统不得继续在全页面搜索并点击 `卖出` 按钮；必须保存截图与 submit 候选 DOM 诊断，并抛出 `Sell dialog disappeared before submit`。Audit 必须将该错误归入 `sell_dialog_open`，而不是继续归入模糊的 `click_submit`。

### SC-38: Portfolio 页面不允许作为 SELL submit 上下文

**Given** 页面只有 portfolio 钱包区/持仓列表的 `卖出` 按钮，但没有 `role=dialog` SELL 确认弹窗  
**When** Bridge 执行 `_click_sell_button()`  
**Then** Bridge 不点击任何 portfolio `卖出` 按钮  
**And** 抛出 `Sell dialog disappeared before submit`  
**And** 保存 `/tmp/trade_sell_submit_context_missing.png` 与 `/tmp/trade_sell_submit_button_candidates.json`  
**And** `/audit` 将该错误归类为 `sell_dialog_open`

### REQ-37: Audit 不得长期保留可识别的 other 失败

Audit 必须持续将重复出现的 `other` 历史失败拆分为具体 bucket。页面导航被 portfolio 跳转打断必须归入 `navigation_race`；Bridge read-only account 不支持 BUY 必须归入 `read_only_account`；执行器 JS `ReferenceError` / `is not defined` 必须归入 `executor_js_error`，但若该记录缺少 market metadata，则按 row-level 规则降级为 `test_or_incomplete_record`。这些分类必须让 `/audit` 的 next-action 队列只保留可行动、可解释的失败类型。

### SC-39: Unknown other 样本被拆分为具体 bucket

**Given** 历史 FAILED 记录包含 `Navigation ... is interrupted by another navigation to .../portfolio`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `navigation_race`  
**Given** 历史 FAILED 记录包含 `Bridge read-only account does not support BUY orders`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `read_only_account` 且不进入 `next_action_candidates`  
**Given** 历史 FAILED 记录缺少 `market_title` 且包含 `Page.evaluate: ReferenceError: bestScore is not defined`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `test_or_incomplete_record`  
**And** `/audit` 不再因为这些样本保留 `other` bucket

### REQ-38: 页面导航网络错误必须统一重试

Bridge 对 Polymtrade 页面导航必须使用统一的 `_goto_with_retry()`。交易页 BUY/SELL 跳转和 portfolio 抓取都不得直接依赖单次 `page.goto(... wait_until="load")`；应使用 `domcontentloaded` 作为更早的稳定点，并对 `ERR_ABORTED`、`net::ERR_CONNECTION_RESET`、`interrupted by another navigation` 和 goto timeout 做 backoff 重试。若 Playwright 报告 transient 导航错误，但当前页面 URL 已经匹配目标 `eventId` / `eventSlug` / `eventSource`，Bridge 必须继续执行，而不是把交易标记为失败。

### SC-40: ERR_CONNECTION_RESET 后重试或接受已到达目标

**Given** 第一次访问 `https://polym.trade/portfolio?eventId=98287&eventSlug=world-cup-group-h-winner&eventSource=polymarket` 时 `page.goto` 抛出 `net::ERR_CONNECTION_RESET`  
**When** 后续重试成功  
**Then** `_goto_with_retry()` 完成且不会抛出交易失败  
**Given** `page.goto` 抛出 transient 网络错误，但当前 URL 已经包含目标 `eventId`、`eventSlug` 与 `eventSource`  
**When** `_goto_with_retry()` 检查目标 URL  
**Then** Bridge 认定目标已到达并继续执行  
**And** `fetch_portfolio_positions()` 使用同一重试机制访问 portfolio 页面

### REQ-39: Audit 必须区分真实 amount input 与历史 BUY 弹窗未打开噪音

Audit 在处理 `amount_input`、`buy_dialog_open`、`click_submit` 等 UI 失败时，必须把零金额或零数量记录降级为 `test_or_incomplete_record`，不得让手工测试/不完整记录挤占 code-fix 队列。对于已有截图证明页面停留在 portfolio/event 页、并未打开 BUY 交易弹窗的历史 `amount_input` 记录，Audit 必须用 record-id exact coverage 标记为 `buy_dialog_open_guard_fixture`，避免已由 BUY 弹窗打开守卫覆盖的旧失败继续进入 `next_action_candidates`。

### SC-41: 历史 amount_input 已覆盖记录不再进入下一步行动队列

**Given** 历史 FAILED 记录 id 598/569/567/565/564/558/508/501/494/481/458/358/355/246 的截图显示没有打开 BUY 交易弹窗  
**When** `/audit` 汇总失败桶  
**Then** 这些记录仍可保留在 `amount_input` bucket 中用于审计可见性  
**And** `covered_count` 等于这些记录数量  
**And** `coverage_ids` 包含 `buy_dialog_open_guard_fixture`  
**And** `uncovered_count` 为 0  
**And** `amount_input` 不进入 `next_action_candidates`  
**Given** 另有 `amount_input`、`buy_dialog_open` 或 `click_submit` 失败记录金额或数量为 0  
**When** `/audit` 应用 row-level 分类  
**Then** 该记录进入 `test_or_incomplete_record`  
**And** 不进入真实 UI code-fix 队列

### REQ-40: Audit 必须收口已由 robust submit fixture 覆盖的历史 click submit

Audit 对 `click_submit` 历史失败必须区分“仍未覆盖的真实提交按钮问题”和“发生于提交按钮加固前、现已由 robust SELL submit fixtures 覆盖的旧样本”。对于 id 597 `Will Argentina win on 2026-06-22?` 这类有效金额/数量但发生于旧执行链路的 SELL submit 失败，Audit 必须保留 bucket 可见性，但标记为 exact covered，避免它继续压过新的 navigation failures。

### SC-42: Argentina SELL submit 历史样本不再进入 next action

**Given** 历史 FAILED 记录 id 597，市场为 `Will Argentina win on 2026-06-22?`，side 为 SELL，错误为 `Could not click sell button`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `click_submit` bucket  
**And** `coverage_ids` 包含 `robust_sell_submit_button_fixtures`  
**And** `covered_count` 为 1  
**And** `uncovered_count` 为 0  
**And** `click_submit` 不进入 `next_action_candidates`

### REQ-41: Audit 必须区分已覆盖 navigation race 与手工关闭噪音

Audit 对 `navigation_race` 必须区分三类：`Page.evaluate` 执行上下文因导航销毁的旧样本、`page.goto` 被 portfolio 自动跳转打断的旧样本，以及手工/不完整记录中页面关闭产生的噪音。前两类若已由 `_evaluate_with_navigation_retry()` 或 `_goto_with_retry()` 测试覆盖，必须标记为 exact covered；`manual-*` 外部交易且 amount/price 为 0 的 page-closed 记录必须降级为 `test_or_incomplete_record`。这样 `/audit` 的下一步队列只保留仍未覆盖的导航问题。

### SC-43: Navigation race 历史样本不再阻塞 next action

**Given** 历史 FAILED 记录 id 581/547/472/350 的错误为 `Page.evaluate: Execution context was destroyed...`  
**When** `/audit` 汇总失败桶  
**Then** 这些记录进入 `navigation_race` bucket  
**And** `coverage_ids` 包含 `evaluate_navigation_retry_fixture`  
**Given** 历史 FAILED 记录 id 450 的错误为 `Page.goto...interrupted by another navigation to .../portfolio`  
**When** `/audit` 汇总失败桶  
**Then** 该记录进入 `navigation_race` bucket  
**And** `coverage_ids` 包含 `goto_interrupted_navigation_retry_fixture`  
**Given** 历史 FAILED 记录 id 574 的 `external_trade_id` 以 `manual-` 开头，且 amount/price 为 0  
**When** `/audit` 应用 row-level 分类  
**Then** 该记录进入 `test_or_incomplete_record`  
**And** `navigation_race.uncovered_count` 为 0  
**And** `navigation_race` 不进入 `next_action_candidates`

### REQ-42: Audit 必须收口已覆盖的 navigation network 历史失败

Audit 对 `navigation_network` 必须区分真实交易页 `ERR_ABORTED` 历史失败和手工/不完整 `ERR_CONNECTION_RESET` 记录。发生在 `_goto_with_retry()` 加固前的真实 BUY `Page.goto: net::ERR_ABORTED` 样本，如果当前 retry 测试已覆盖该错误类型，必须标记为 exact covered。`manual-*` 外部交易且 amount/price 为 0 的网络导航失败必须降级为 `test_or_incomplete_record`。在当前 500 条/100 失败审计窗口内，所有 code/infra bucket 若已 covered 或降级，`next_action_candidates` 应为空。

### SC-44: Navigation network 历史样本不再进入 next action

**Given** 历史 FAILED 记录 id 559/542/473/439/372/365/235 的错误为 `Page.goto: net::ERR_ABORTED...`  
**When** `/audit` 汇总失败桶  
**Then** 这些记录进入 `navigation_network` bucket  
**And** `coverage_ids` 包含 `goto_network_retry_fixture`  
**And** `navigation_network.covered_count` 为 7  
**And** `navigation_network.uncovered_count` 为 0  
**Given** 历史 FAILED 记录 id 592 的 `external_trade_id` 以 `manual-` 开头，且 amount/price/quantity 为 0  
**When** `/audit` 应用 row-level 分类  
**Then** 该记录进入 `test_or_incomplete_record`  
**And** `next_action_candidates` 为空

### REQ-43: Audit 必须支持修复后新增失败过滤

Bridge `/audit` 接口和 `bridge_reliability_audit.py` CLI 必须支持 `since_ms` / `--since-ms` 参数，用于只统计指定时间之后创建或更新的 recent PENDING/FAILED 记录。该过滤不得影响 SUCCESS ledger 与 live portfolio 的全量持仓一致性检查；输出 metrics 必须同时包含过滤后 `records_checked`、未过滤 `raw_records_checked` 和生效的 `since_ms`，便于日报或 loop 只观察修复后新增执行问题。

### SC-45: since_ms 过滤只影响 recent failure 队列

**Given** `/audit` 被调用时携带未来时间戳 `since_ms`  
**When** Bridge 运行 reliability audit  
**Then** `metrics.raw_records_checked` 仍等于读取的最近记录数  
**And** `metrics.records_checked` 为 0  
**And** `metrics.recent_failure_count` 为 0  
**And** `failure_buckets` 为空  
**And** `next_action_candidates` 为空  
**And** SUCCESS ledger / portfolio mismatch 检查仍使用 `ledger_limit` 指定的全量 SUCCESS 记录

### REQ-44: Audit metrics 必须暴露 post-fix 监控水位

Bridge `/audit` 和 CLI 输出必须暴露足够的时间水位与可行动计数，让 loop 能判断当前 `since_ms` 窗口是否真的没有新增失败。Metrics 必须包含未过滤最近记录最新时间、过滤后最近记录最新时间、过滤后最新失败时间，以及可行动 failure bucket 数。

### SC-46: Future since_ms 窗口输出空 filtered 水位

**Given** `/audit` 被调用时携带未来时间戳 `since_ms`  
**When** Bridge 运行 reliability audit  
**Then** `metrics.latest_raw_record_time_ms` 等于未过滤最近记录中的最大 created/updated 时间  
**And** `metrics.latest_record_time_ms` 为 null  
**And** `metrics.latest_failure_time_ms` 为 null  
**And** `metrics.actionable_failure_bucket_count` 为 0

### REQ-45: Audit 必须输出可直接消费的 monitor status

Bridge `/audit` 和 CLI 输出必须包含 `monitor_status` 对象，让自动 loop、日报或前端无需重新解释底层 metrics 即可判断当前窗口是否需要行动。`monitor_status.status` 必须至少支持 `actionable`、`clear`、`no_recent_records` 三种状态，并携带 message、actionable bucket 数、pending timeout 数、recent failure 数、时间水位、`since_ms` 和下一步 bucket 列表。

### SC-47: monitor_status 区分清空窗口与无记录窗口

**Given** 默认 `/audit` 窗口存在历史 FAILED 记录，但 `next_action_candidates` 为空  
**When** Bridge 运行 reliability audit  
**Then** `monitor_status.status` 为 `clear`  
**And** `monitor_status.actionable_failure_bucket_count` 为 0  
**And** `monitor_status.next_action_buckets` 为空  
**Given** `/audit` 被调用时携带未来时间戳 `since_ms`  
**When** Bridge 运行 reliability audit  
**Then** `monitor_status.status` 为 `no_recent_records`  
**And** `monitor_status.latest_record_time_ms` 为 null  
**And** `monitor_status.latest_failure_time_ms` 为 null

### REQ-46: 后端与统计页必须消费 Bridge monitor status

PolyHermes 后端必须提供正式只读 Bridge audit 代理接口，避免前端直接访问 polymtrade-bridge 8080 端口。该接口必须调用 Bridge `/audit` 并返回 `monitor_status`、metrics 和 next action candidates。统计信息页必须消费该接口，在用户刷新统计时同步展示 Bridge 执行链路状态、可处理失败桶、最近失败数、Pending 超时、持仓快照数量、最近记录水位和下一步 bucket，让 loop 监控结果可以被人工直接看到。

### SC-48: 统计页显示 clear/actionable/no_recent_records 状态

**Given** Bridge `/audit` 返回 `monitor_status.status=clear`  
**When** 用户打开或刷新统计信息页  
**Then** 页面显示 Bridge 执行链路监控状态为正常  
**And** 可处理失败桶为 0  
**Given** Bridge `/audit` 返回 `monitor_status.status=actionable` 且包含 `next_action_buckets`  
**When** 用户打开或刷新统计信息页  
**Then** 页面显示需处理状态  
**And** 展示前几个下一步 bucket 及未覆盖/总数量  
**Given** Bridge `/audit` 暂不可用  
**When** 后端代理接口返回错误  
**Then** 统计页保留其它统计数据加载流程，并将 Bridge audit 区域显示为暂无返回

### REQ-47: 系统必须提供优化点日报页面

PolyHermes 必须提供一个可从左侧菜单进入的优化点日报页面，用于承载 loop engineering 的日常执行结果。页面必须展示当前 Bridge audit 状态、最近 24 小时 post-fix 窗口状态、可行动失败桶、Pending 超时、最近失败水位，以及近期已经完成的 Bridge 优化点。页面刷新时必须重新读取后端正式 audit 代理接口，不得只显示静态文字。

### SC-49: 优化点日报显示 live audit 与 24 小时窗口

**Given** 用户进入 `/optimization-daily`  
**When** 页面加载  
**Then** 页面调用后端 Bridge audit 代理接口读取默认窗口  
**And** 页面再次调用同一代理接口读取 `sinceMs=now-24h` 的 post-fix 窗口  
**And** 当前审计窗口显示 `monitor_status.status`、可处理失败桶、Pending 超时、最近失败数、持仓快照和最近记录时间  
**And** 最近 24 小时窗口显示窗口记录数、可处理失败桶、最近失败数、Pending 超时和最近失败时间  
**And** 若任一窗口存在 next action bucket，页面展示下一步处理桶标签

### REQ-48: Portfolio 与通用页面导航必须有 commit fallback

Bridge 对 Polymtrade 的启动页、portfolio 页、钱包地址提取和调试导航必须统一使用 `_goto_with_retry()`，不得继续直接依赖 `page.goto(... wait_until="load")`。当 `domcontentloaded` 导航连续遇到 `ERR_CONNECTION_RESET`、`ERR_NETWORK_CHANGED`、`ERR_NETWORK_IO_SUSPENDED`、`ERR_ABORTED`、被其它导航打断或 goto timeout 等 transient 错误时，Bridge 必须在常规重试耗尽后尝试 `commit` 级别 fallback，并在目标 URL 已经到达时继续执行。Portfolio 持仓抓取必须允许更多重试，以降低短暂网络抖动造成 `/portfolio` 500、SELL 前持仓校验失败或统计快照缺失的概率。

### SC-50: 连续 transient portfolio 导航错误后使用 commit fallback

**Given** `page.goto("https://polym.trade/portfolio", wait_until="domcontentloaded")` 连续返回 `net::ERR_CONNECTION_RESET`  
**When** `_goto_with_retry()` 已耗尽常规重试  
**Then** Bridge 尝试 `page.goto(..., wait_until="commit")`  
**And** 即使后续 `wait_for_load_state("domcontentloaded")` 超时，也允许调用方继续等待页面动态内容  
**Given** Bridge 启动后调用 `/portfolio`  
**When** Polymtrade 页面最终可访问  
**Then** `/portfolio` 返回持仓列表而不是因为前几次 transient 导航错误直接 500

### REQ-49: Bridge 必须明确暴露实际跟单账号选择

Bridge copy-trading rule engine 必须把 `COPY_TRADING_ACCOUNT_ID` 解析为正整数；空字符串、`0`、负数和非法字符串必须视为未设置，不得作为 `copy_trading.account_id` 过滤条件。Bridge 启动时若能从当前钱包解析出 PolyHermes `wallet_accounts.id`，必须优先使用检测账号；只有当环境变量明确配置了不同的正整数时才输出 mismatch warning。`/status` 必须暴露当前实际使用的 copy-trading account id 和已加载配置数量，便于确认 Bridge 没有跟错账号。

### SC-51: 空 env 不再产生 account mismatch warning

**Given** `COPY_TRADING_ACCOUNT_ID` 未设置或为空  
**And** 当前 Polymtrade 钱包能解析为 account id 2  
**When** Bridge 启动 copy-trading rule engine  
**Then** rule engine 使用 account id 2 过滤配置  
**And** 日志输出使用 detected account id 的 info 记录  
**And** 不输出 `COPY_TRADING_ACCOUNT_ID mismatch: env=0` warning  
**And** `/status` 返回 `copy_trading_account_id=2` 与实际加载的配置数量

### REQ-50: 优化点日报必须显示 Bridge runtime 跟单状态

优化点日报页面必须读取 Bridge runtime `/status`，并展示执行器 ready 状态、登录状态、实际跟单 account id、有效配置数量和最近错误。该页面必须通过本地 dev proxy 访问 Bridge runtime，避免浏览器跨域失败。若 account id 为空、配置数量为 0、未登录或 executor 未 ready，页面必须能明显显示异常状态，方便在 BUY/SELL 执行前发现跟错账号或无配置风险。

### SC-52: 页面展示当前实际跟单账号与配置数

**Given** Bridge `/status` 返回 `ready=true`、`logged_in=true`、`copy_trading_account_id=2`、`copy_trading_config_count=2`  
**When** 用户进入 `/optimization-daily` 或点击刷新  
**Then** 页面通过 `/bridge-runtime/status` 读取 Bridge runtime 状态  
**And** 页面显示 Bridge 在线  
**And** 页面显示跟单账号 ID 为 2  
**And** 页面显示有效配置数为 2

### REQ-51: 后端必须正式代理 Bridge runtime status

PolyHermes 后端必须提供正式只读接口代理 Bridge runtime `/status`，避免生产页面依赖 Vite dev proxy 或浏览器跨域访问 8080。该接口必须返回 ready、logged in、last error、实际 copy-trading account id 和 copy-trading config count。优化点日报必须优先调用后端正式接口；仅在开发环境后端尚未重启或接口暂不可用时，才允许回退到 `/bridge-runtime/status`。

### SC-53: 优化点日报优先使用正式 status API

**Given** 后端 `/api/bridge/trades/status` 返回成功  
**When** 用户打开或刷新 `/optimization-daily`  
**Then** 页面使用正式 API 返回的 runtime status 展示 Bridge 运行状态  
**And** 不需要浏览器直接跨域访问 8080  
**Given** 后端正式 status API 暂不可用但 Vite dev proxy 可用  
**When** 用户在本地开发环境打开优化点日报  
**Then** 页面回退读取 `/bridge-runtime/status`  
**And** 仍能显示 ready、logged in、account id 与配置数量

### REQ-52: Bridge 后端代理变更必须完成 Kotlin 编译验证

涉及 Bridge audit、Bridge runtime status、Bridge trade record DTO 或 Controller 的后端变更，必须在可用 JDK 环境下运行 `./gradlew compileKotlin`。本项目可使用 `jdk17/Contents/Home` 作为 `JAVA_HOME`。编译失败不得视为完成；若本机系统 Java 不可用，loop 必须先尝试项目内 JDK，再报告验证结果。

### SC-54: 项目内 JDK17 可验证 Bridge 后端代理

**Given** 系统 `/usr/libexec/java_home` 无法找到 Java Runtime  
**And** 项目存在 `jdk17/Contents/Home`  
**When** loop 验证 Bridge 后端代理变更  
**Then** 使用 `JAVA_HOME=<project>/jdk17/Contents/Home ./gradlew compileKotlin`  
**And** 编译必须成功，证明 `/api/bridge/trades/audit` 与 `/api/bridge/trades/status` 的 DTO、Client 和 Controller 代码可编译

### REQ-53: Bridge audit 必须携带 runtime status

Bridge `/audit` 在线接口必须在顶层返回 `runtime_status`，包含 executor ready、login state、last error、实际 copy-trading account id 和 copy-trading config count。后端正式 audit 代理和前端类型必须透传该字段。优化点日报应优先使用 audit 响应内的 runtime status，只有 audit 未携带该字段时才额外调用 status 接口或开发代理。这样单次 audit 即可判断交易失败状态与当前执行条件，减少前端多请求带来的漂移。

### SC-55: 单次 audit 返回执行链路状态与账号配置

**Given** Bridge executor ready 且已登录  
**And** rule engine 当前使用 account id 2 且加载 2 条配置  
**When** 调用 `/audit`  
**Then** 响应 `monitor_status` 仍显示当前 failure 窗口状态  
**And** 响应顶层 `runtime_status.ready=true`  
**And** `runtime_status.logged_in=true`  
**And** `runtime_status.copy_trading_account_id=2`  
**And** `runtime_status.copy_trading_config_count=2`  
**And** 优化点日报使用该 `runtime_status` 展示 Bridge 运行状态

### REQ-54: Runtime 异常必须阻断 audit monitor clear 状态

Bridge 在线 `/audit` 的 `monitor_status` 必须把 runtime readiness 纳入判断。若 executor 未 ready、未登录、copy-trading account id 缺失、copy-trading config count 为 0，或存在 last error，则即使 post-fix 窗口没有 PENDING/FAILED 记录，`monitor_status.status` 也必须为 `runtime_blocked`，并返回 `runtime_block_reasons`。只有 runtime 健康时，原有 `clear`、`actionable`、`no_recent_records` 才能保持原义。

### SC-56: Runtime 未就绪时 audit 显示 runtime_blocked

**Given** audit 底层 failure bucket 为空  
**And** runtime status 为 `ready=false`、`logged_in=false`、`copy_trading_account_id=null`、`copy_trading_config_count=0`、`last_error=browser closed`  
**When** 调用在线 `/audit`  
**Then** 顶层 `runtime_status` 仍原样返回  
**And** `monitor_status.status=runtime_blocked`  
**And** `monitor_status.runtime_block_reasons` 包含 `executor_not_ready`、`not_logged_in`、`copy_trading_account_missing`、`copy_trading_config_empty`、`last_error_present`  
**Given** runtime status 健康  
**When** 调用在线 `/audit`  
**Then** `monitor_status.status` 保持原有 failure-window 判断结果  
**And** 不返回 runtime block reasons

### REQ-55: 优化点日报必须用中文展示 runtime block 原因

优化点日报在 `monitor_status.status=runtime_blocked` 时，必须把 `runtime_block_reasons` 转换为操作者可直接理解的中文标签。至少应覆盖执行器未就绪、Bridge 未登录、跟单账号缺失、有效配置为 0、存在最近错误五类原因。页面不得只展示内部英文 key。

### SC-57: Runtime block 原因显示为中文标签

**Given** audit 返回 `monitor_status.status=runtime_blocked`  
**And** `runtime_block_reasons` 包含 `executor_not_ready`、`not_logged_in`、`copy_trading_account_missing`、`copy_trading_config_empty`、`last_error_present`  
**When** 用户打开优化点日报  
**Then** Bridge 运行状态卡片显示红色原因标签  
**And** 标签文本包含 `执行器未就绪`、`Bridge 未登录`、`跟单账号缺失`、`有效配置为 0`、`存在最近错误`

### REQ-56: 统计信息页必须同步展示 runtime block 原因

统计信息页的 Bridge 执行链路监控卡片必须识别 `monitor_status.status=runtime_blocked`，并显示为红色“执行受阻”状态。若 audit 返回 `runtime_block_reasons`，统计信息页必须将内部英文 key 映射为中文原因标签，至少覆盖执行器未就绪、Bridge 未登录、跟单账号缺失、有效配置为 0、存在最近错误五类原因。统计信息页不得与优化点日报对同一个 audit 状态展示不一致。

### SC-58: 统计信息页显示执行受阻与中文原因

**Given** audit 返回 `monitor_status.status=runtime_blocked`
**And** `runtime_block_reasons` 包含 `executor_not_ready`、`not_logged_in`、`copy_trading_account_missing`、`copy_trading_config_empty`、`last_error_present`
**When** 用户打开或刷新 `/statistics`
**Then** Bridge 执行链路监控卡片状态显示红色 `执行受阻`
**And** 原因标签显示 `执行器未就绪`、`Bridge 未登录`、`跟单账号缺失`、`有效配置为 0`、`存在最近错误`

### REQ-57: Portfolio enrichment 不得用错误 eventSlug 污染持仓元数据

Bridge `/portfolio` 抓取持仓后，若卡片 href 或当前轮播 URL 暴露的 `eventSlug` 对应事件中没有与 portfolio `marketTitle` 同标题的 market，enrichment 不得回退使用该事件的第一个 market。系统必须继续使用 portfolio 标题做 Gamma market title search；title search 结果也必须要求 market question 与 portfolio 标题规范化后一致，找不到 exact match 时不得采用首条结果。只有 market question 与 portfolio 标题规范化后一致时，才能返回 `conditionId`、`marketSlug` 与 `eventSlug`。该规则用于避免多个不同持仓被错误归到同一个 current carousel event 或同一个 Gamma 搜索首条结果，从而降低 SELL live position 匹配漂移。

### SC-59: 错 href eventSlug 不能覆盖正确 title search

**Given** portfolio 持仓标题为 `Will Spain win Group H in the 2026 FIFA World Cup?`
**And** 该卡片 href 暂时携带 `eventSlug=new-rhianna-album-before-gta-vi-926`
**And** 该错误事件的第一个 market 是 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?`
**When** Bridge 执行 portfolio enrichment
**Then** Bridge 不返回错误事件第一个 market 的 `conditionId`
**And** Bridge 继续通过 title search 找到 `Will Spain win Group H in the 2026 FIFA World Cup?` 的真实 `conditionId`、`marketSlug` 与 `eventSlug`
**Given** Gamma title search 只返回不相关的首条 market
**When** portfolio 标题与该 market question 规范化后不一致
**Then** Bridge 不返回该不相关 market 的 `conditionId`

### REQ-58: Portfolio enrichment 必须保持只读

Bridge `/portfolio` 的 enrichment 流程不得点击 portfolio 卡片、不得依赖并发页面点击来揭示 `eventSlug`，也不得因为 enrichment 改变当前 portfolio carousel URL。`fetch_portfolio_positions()` 可以并发调用只读 Gamma API，但不能让每个持仓 enrichment 在同一个 Playwright page 上执行点击或导航。若只读的 href、eventSlug、title search 都无法 exact match，系统必须返回缺失 metadata，而不是通过 UI 点击尝试猜测。

### SC-60: Enrichment 无 exact match 时不点击 portfolio 卡片

**Given** portfolio page 当前 URL 为 `/portfolio`
**And** Gamma market/title/event search 都没有返回与 portfolio 标题 exact match 的 market
**When** Bridge 执行 `_enrich_position()`
**Then** Bridge 返回空 metadata
**And** 不调用 `eval_on_selector_all()` 或其它 portfolio 卡片点击逻辑

### REQ-59: Portfolio 抓取必须等待持仓行渲染

Bridge `/portfolio` 导航到 Polymtrade portfolio 页面后，必须等待当前持仓行渲染，或等待页面出现明确空持仓状态后，才执行持仓列表解析。若页面已经显示 portfolio shell 但持仓行尚未插入 DOM，系统不得立即返回 0 positions。该等待必须能容忍短暂 navigation race，避免 SELL live precheck 在页面刚加载、刚重启或 audit 并发请求时误判无持仓。

### SC-61: 延迟渲染持仓行时等待后再解析

**Given** portfolio 页面先显示 `投资组合` 与 `持仓` shell
**And** 持仓 `li.flex px-4 py-2...cursor-pointer` 行在 250ms 后才插入 DOM
**When** Bridge 执行 portfolio rows wait
**Then** 等待返回 true
**And** 后续 `/portfolio` 解析不会因为初始 shell 已显示但列表未渲染而返回 0 positions

### REQ-60: 世界杯小组冠军持仓必须支持高置信只读 metadata 补全

Bridge `/portfolio` enrichment 对标题形如 `Will <team> win Group <letter> in the 2026 FIFA World Cup?` 的持仓，必须能推导 `world-cup-group-<letter>-winner` 事件 slug，并通过 Gamma events slug 查询读取该事件下的 markets。即使 Gamma `markets?title=` 返回不相关结果，也必须优先使用该 derived event slug 路径；但仍必须要求 market question 与 portfolio 标题规范化后一致，不能因为 derived event slug 命中事件就回退使用事件首个 market。

### SC-62: Spain Group H 使用 derived event slug 补全

**Given** portfolio 持仓标题为 `Will Spain win Group H in the 2026 FIFA World Cup?`
**And** Gamma `markets?title=` 会返回不相关的 GTA VI market
**And** Gamma `events?slug=world-cup-group-h-winner` 返回包含 `Will Spain win Group H in the 2026 FIFA World Cup?` 的 markets
**When** Bridge 执行 `_enrich_position()`
**Then** Bridge 返回 Spain Group H 的真实 `conditionId`
**And** `marketSlug=will-spain-win-group-h-in-the-2026-fifa-world-cup`
**And** `eventSlug=world-cup-group-h-winner`
**And** 不调用或不采用不相关的 Gamma title search 结果

### REQ-61: Runtime status 可从单账号配置推断 copy-trading account

Bridge 启动时若当前钱包 account id 检测暂时失败，但 copy-trading rule engine 已加载到有效配置，且所有配置都属于同一个 `account_id`，`active_account_id` 和 `/status.copy_trading_account_id` 必须返回该唯一账号，避免误报 `copy_trading_account_missing` 导致 audit `runtime_blocked`。若已加载配置跨多个 account id，系统不得猜测账号，仍必须返回空 account id 并保持 runtime block。

### SC-63: 单账号配置可解除 account missing

**Given** `COPY_TRADING_ACCOUNT_ID` 未设置
**And** 钱包 account id 检测暂时失败
**And** rule engine 已加载 2 条 enabled config，且二者 `account_id=2`
**When** 调用 `/status`
**Then** `copy_trading_account_id=2`
**And** `copy_trading_config_count=2`
**And** audit runtime gate 不返回 `copy_trading_account_missing`
**Given** rule engine 已加载配置分别属于 account 2 和 account 3
**When** 调用 `/status`
**Then** `copy_trading_account_id` 为空
**And** audit runtime gate 仍返回 `copy_trading_account_missing`

### REQ-62: Portfolio enrichment 必须支持 exact market slug 反查

Bridge `/portfolio` enrichment 在已有 `marketSlug` 或能从 portfolio `marketTitle` 推导出 market slug 时，必须调用 Gamma markets 的 `slug` 参数进行精确反查，而不是把 slug 当成 `title` 参数搜索。反查结果仍必须要求 market question 与 portfolio 标题规范化后一致；若 slug 命中不到 market，或返回 market question 与 portfolio 标题不一致，系统必须返回空 metadata 或继续后续安全路径，不得采用不相关搜索结果。该规则用于补齐政治、体育等单市场持仓的 `conditionId/marketSlug/eventSlug`，提升 SELL live precheck 对现有持仓的匹配质量。

### SC-64: Abelardo 政治持仓通过 derived market slug 补全

**Given** portfolio 持仓标题为 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?`
**And** Gamma `markets?title=` 返回不相关的 GTA VI markets
**And** 从标题可推导 market slug `will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election`
**And** Gamma `markets?slug=will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election` 返回同标题 market
**When** Bridge 执行 `_enrich_position()`
**Then** Bridge 返回 Abelardo market 的真实 `conditionId`
**And** `marketSlug=will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election`
**And** `eventSlug=colombia-presidential-election`
**And** 不采用不相关的 Gamma title search 首条结果

### REQ-63: Audit stale success mismatch 不得触发 active/actionable 状态

Bridge `/audit` 必须区分 fresh、stale 与 operator reconciled 的 success ledger vs live portfolio mismatch。`stale_success_position_mismatch_count` 必须保留用于历史复盘，但不得计入 `active_success_position_mismatch_count`、`monitor_status.actionable_issue_count` 或 CLI `--strict` 退出码。只有 fresh success mismatch、pending timeout、或未覆盖的 actionable failure bucket 才能触发 active/actionable。该规则用于避免历史已人工平仓、外部平仓或旧账本噪音长期污染 SELL 成功率监控。

### SC-65: 全部 mismatch 为 stale 时 audit 仍显示无当前行动项

**Given** 最近窗口没有 PENDING/FAILED 记录
**And** audit 发现 13 条 `stale_success_position_mismatch`
**And** `fresh_success_position_mismatch_count=0`
**When** Bridge 生成 `/audit` 结果
**Then** `success_position_mismatch_count=13`
**And** `stale_success_position_mismatch_count=13`
**And** `active_success_position_mismatch_count=0`
**And** `monitor_status.actionable_issue_count=0`
**And** CLI `bridge_reliability_audit.py --strict` 退出码为 0

### REQ-64: Audit 必须为 stale mismatch 输出只读 reconciliation suggestions

Bridge `/audit` 对未被 operator reconciliation 注释、且已判定为 `stale_success_position_mismatch` 的账本错配，必须输出 `reconciliation_suggestions`。每条 suggestion 必须包含 reconciliation key、建议 status、confidence、market id/title/outcome/outcome_index、expected/actual quantity、latest record 信息、contributing record ids，以及可提交到 `/audit/reconciliations` 的 `annotation_payload`。该输出只用于人工确认和后续落库，不得自动写入 reconciliation 文件，不得改变 `actionable_issue_count`，也不得为 fresh success mismatch 生成建议。

### SC-66: Stale mismatch 生成 accepted_stale 建议但不改变 actionable

**Given** audit 发现 13 条未注释的 `stale_success_position_mismatch`
**And** `fresh_success_position_mismatch_count=0`
**When** Bridge 生成 `/audit` 结果
**Then** `reconciliation_suggestion_count=13`
**And** `reconciliation_suggestions[0].status=accepted_stale`
**And** `reconciliation_suggestions[0].annotation_payload.status=accepted_stale`
**And** `reconciliation_suggestions[0].annotation_payload.actor=audit_suggestion`
**And** `monitor_status.actionable_issue_count=0`
**And** fresh success mismatch 不出现在 `reconciliation_suggestions`

### REQ-65: 优化点日报必须展示 reconciliation suggestions

后端正式 Bridge audit DTO 必须透传 `/audit` 的 `reconciliation_suggestions`、`reconciliation_suggestion_count`、active/fresh/stale/reconciled/unresolved success mismatch 指标和 `monitor_status.actionable_issue_count`。优化点日报必须展示历史错配复盘建议模块，包含历史错配数量、当前错配数量、复盘建议数量、可行动问题数量，并列出建议的 confidence、market title、latest record、outcome、expected/actual quantity 与建议状态。该展示必须保持只读，不得自动调用 `/audit/reconciliations` 写入注释。

### SC-67: 日报展示前 8 条历史错配建议

**Given** 后端 audit 响应包含 13 条 `reconciliationSuggestions`
**And** `metrics.reconciliationSuggestionCount=13`
**When** 用户打开 `/optimization-daily`
**Then** 页面显示 `历史错配复盘建议`
**And** 显示历史错配、当前错配、复盘建议、可行动问题 4 个统计值
**And** 表格展示最多前 8 条建议
**And** 每条建议展示置信度、市场、latest record id、outcome、账本/实仓数量和建议状态
**And** 页面不提供自动写入 reconciliation 的操作

### REQ-66: Reconciliation suggestions 必须支持人工确认写入

PolyHermes 后端必须提供正式 Bridge reconciliation 代理接口，用于读取 `/audit/reconciliations` 注释和写入单条人工确认。写入接口必须校验 status、marketId 与 outcome，并只允许 `externally_closed`、`manual_closed`、`accepted_stale`、`wrong_market_known`。优化点日报的每条 reconciliation suggestion 必须提供显式 `确认` 操作，点击后必须弹出二次确认说明，确认后才调用后端代理写入 reconciliation。写入成功后页面必须刷新 audit。系统不得自动批量写入 suggestions。

### SC-68: 人工确认 stale suggestion 后刷新 audit

**Given** `/optimization-daily` 表格显示一条 `accepted_stale` suggestion
**When** 用户点击该行 `确认`
**Then** 页面弹出 `确认历史错配建议`
**When** 用户在弹窗中确认
**Then** 前端调用 `/api/bridge/trades/audit/reconciliations/upsert`
**And** 请求体包含 suggestion 的 status、marketId、marketTitle、outcome、outcomeIndex、note 与 actor
**And** 保存成功后提示 `已确认历史错配`
**And** 页面重新拉取 audit 数据
**And** 未点击确认时不得写入 reconciliation

### REQ-67: 手工零金额 SELL 历史失败不得进入代码修复队列

Bridge audit 必须识别 `manual-*` 外部 id、amount 或 price 为 0 的 SELL 历史测试/不完整记录。若这类记录被错误文本归类为 `sell_post_submit_no_effect` 或 `live_position_insufficient`，audit 必须将其降级为 `test_or_incomplete_record`，避免手工测试、未完整入账或零金额样本长期占用 SELL 代码修复队列。该降级仅适用于 `manual-*` 且零金额/零价格记录；真实外部 id 且非零金额/价格的 SELL post-submit 无效果失败必须继续保留原始 bucket 与 uncovered 状态。

### SC-69: 手工零金额 SELL 记录降级但真实 post-submit 失败保留

**Given** 历史记录 id 572 的 `external_trade_id` 以 `manual-` 开头
**And** `amount=0` 或 `price=0`
**And** error message 为 `SELL post-submit verification failed`
**When** Bridge audit 对该记录分类
**Then** 分类结果为 `test_or_incomplete_record`
**And** 不出现在 `next_action_candidates`
**Given** 另一条真实 SELL 记录的 `external_trade_id` 不是 `manual-*`
**And** `amount>0` 且 `price>0`
**And** error message 同样为 `SELL post-submit verification failed`
**When** Bridge audit 对该记录分类
**Then** 分类结果仍为 `sell_post_submit_no_effect`
**And** 未被 coverage 覆盖时保留 uncovered 状态

### REQ-68: Deposit/balance modal 必须归类为资金不足而非网络/代币选择

Bridge audit 对错误文本中明确包含 `insufficient balance`、`insufficient USDC balance`、`needs a deposit` 或中文 `余额不足` 的失败，必须优先归类为 `insufficient_balance`。即使同一错误文本也包含 `Network/deposit modal` 或 modal 相关描述，也不得归类为 `network_or_token_modal`。只有没有明确资金不足/充值含义的 network/token modal 才保留 `network_or_token_modal`，用于后续 UI modal 处理优化。该规则用于区分账户资金/配置问题与 Bridge 浏览器执行链路问题，避免历史资金不足样本污染 BUY/SELL 代码修复队列。

### SC-70: 资金不足 modal 不再占用 network_or_token_modal bucket

**Given** Bridge 失败错误为 `Network/deposit modal keeps blocking the trade. The Bridge account probably has insufficient USDC balance or needs a deposit.`
**When** Bridge audit 对错误分类
**Then** 分类结果为 `insufficient_balance`
**And** actionability 为 `state_or_risk`
**And** 不出现在 `next_action_candidates`
**Given** 另一条错误为 `Network/token modal keeps blocking the trade`
**When** Bridge audit 对错误分类
**Then** 分类结果仍为 `network_or_token_modal`

### REQ-69: BUY/SELL 遇到 deposit/balance modal 必须立即中止

Bridge 执行 BUY 或 SELL 时，若网络/代币选择弹窗中明确出现 `deposit`、`充值`、`insufficient`、`余额不足` 或 `not enough` 等资金不足信号，系统必须立即中止当前交易并抛出资金/充值状态错误。系统不得继续尝试选择 Polygon/USDC、不得关闭或强制隐藏该 modal 后继续输入金额或提交订单。普通 network/token selection modal 仍可按既有逻辑选择 Polygon/USDC 并确认。该规则用于减少余额不足账户上的无效点击、缩短失败路径，并让后续 audit 稳定归入 `insufficient_balance` 而非 BUY/SELL selector 失败。

### SC-71: Deposit modal 不触发 Polygon/USDC 点击

**Given** 页面显示 `选择网络和代币` modal
**And** modal 文案包含 `Insufficient balance. Please deposit.`
**When** Bridge 执行 modal 检测
**Then** `_is_network_modal_open()` 返回 true
**And** `_is_deposit_or_insufficient_modal_open()` 返回 true
**When** Bridge 尝试处理该 modal
**Then** 不点击 `Polygon`
**And** 不点击 `USDC`
**And** BUY/SELL 执行链路抛出包含 `Insufficient balance` 或 `deposit modal` 的错误
**Given** 页面显示普通 `选择网络和代币` modal
**And** modal 不包含资金不足/充值文案
**When** Bridge 尝试处理该 modal
**Then** 仍可选择 `Polygon` 与 `USDC` 并确认
