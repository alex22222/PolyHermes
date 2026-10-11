# Future BTC 5 分钟：准备完成后自动点击一次

脚本：[future_btc5m_buy_once.js](../scripts/future_btc5m_buy_once.js)。它是独立、由用户启动的脚本，不在扩展 manifest 中，也不会随生产页面自动运行。加载文件只定义方法，默认启动为模拟模式。

脚本每 500 毫秒读取现有助手的准备状态，等待**启动后新生成的本轮 READY**。随后核对真实页面的美元市价买入票据：金额必须恰为 `1`，当前选中方向、READY 方向和涨/跌按钮数字较大的一方必须一致。条件通过时，实盘模式点击票据内唯一的“买入 涨”或“买入 跌”，随后停止；每次启动最多尝试一次。

这次只完成代码与模拟测试，没有启动实盘、点击真实买入、接入服务器交易执行器或改变项目开关。生产页面的订单列表不会因此生成平台订单回执；点击尝试与订单提交、实际成交分别核对。

## 使用步骤

1. 保持现有 Mac 助手、私有隧道和已登录的 Future BTC 5 分钟页面运行。
2. 本脚本需要本次新增的两个只读助手导出。由你在 `chrome://extensions` 对 **PolyHermes Future BTC 5m 助手**重新加载，然后刷新 Future 页面。本次没有增加扩展权限或自动加载买入脚本。
3. 在 Future 标签页打开开发者工具的 Console，选择 **PolyHermes Future BTC 5m 助手**的内容脚本执行上下文。普通 `top` 页面上下文不能访问助手的隔离变量和后台消息。先输入 `typeof globalThis.FutureBtc5m?.findAmountTicket`，正确上下文应返回 `"function"`；缺少变量或导出时先处理上下文/扩展更新问题。
4. 将上述脚本文件的完整内容加载到这个上下文。只加载定义不会发送请求或点击。默认模拟：

   ```javascript
   FutureBtc5mBuyOnce.start()
   ```

5. 在下一轮第 60 秒之前启动监控，并在项目页开启现有“自动准备票据”开关。启动前已经生成的 READY 会被忽略，等待新票据，不追买旧记录。查看结果：

   ```javascript
   FutureBtc5mBuyOnce.status()
   ```

   模拟通过返回 `DRY_RUN_READY`，包含轮次、方向、`amountUsd: 1`；不会点击或写入买入占用记录。

6. 如决定使用实际点击，由你在同一上下文运行下面的命令。模拟通过或停止后可以重新启动，但仍只接受新启动之后创建的票据：

   ```javascript
   FutureBtc5mBuyOnce.start({live: true})
   ```

   点击尝试后返回 `CLICK_ATTEMPTED`，原因 `PLATFORM_RESULT_UNKNOWN`。请在 Future 查验实际订单和成交；脚本不处理额外确认、钱包签名、成交回执或失败补单。

停止等待：

```javascript
FutureBtc5mBuyOnce.stop()
```

停止会取消待处理的异步检查；已经发生的点击尝试不会被撤销，`status()` 继续保留尝试事实。完整刷新或页面重载后脚本定义消失，需要由你重新加载。已经尝试过点击的脚本实例不能再次启动；跨重载的同轮占用也不会自动清除。不要删除占用记录来重试不确定的订单。

## 核对与去重

- 只接受 `PREPARE_ONLY`、`USER_REQUEST`、schema2 的当前 READY；当前 intent 必须为空，准备回执必须确认本轮方向与 $1。
- 保留现有入场窗口：本轮第 60 秒至第 80 秒之前。原始价格和按钮快照在认领、READY 和当前检查时均须不超过 5 秒；读取状态不延长原始许可。
- 涨/跌数字相同、缺失、较大侧改变、金额改变、旧页面标题、按钮禁用或歧义均拒绝。脚本不重新填写金额、不切换方向，不使用默认涨兜底。
- 实盘必须有 Web Locks。持锁后再读取一次 READY、检查当前 DOM，并先写入唯一的本地占用键 `polyhermes.future-btc5m.buy-once`。存储失败就停止，不接触其它存储键或登录资料。
- 写入占用后，在无 `await` 的最后阶段再次核对时效、票据和同一个已连接按钮，避免慢存储或页面变化造成过期点击。此阶段拒绝显示 `BLOCKED / FINAL_CHECK_FAILED`，已写占用仍保留；没有点击也不自动补试。
- 同一浏览器配置中，共享相同 Future origin 的实例由 Web Lock 和 localStorage 去重；不保证不同设备、不同配置或不同 origin 之间互斥。点击抛异常也视为已占用，不重试、不宣称成交。
- `BLOCKED` 表示监控已停止，须查看 `reason`；`WATCHING` 表示仍等待有效的新 READY。缺少扩展上下文或 Web Locks 时启动会报错，不降级执行。

## 验证

测试使用现有 `content.js` 的真实检查方法和隔离的模拟票据、时钟、存储、锁及后台消息，不连接浏览器或真实账户。

```bash
node --check scripts/future_btc5m_buy_once.js
node --test scripts/test_future_btc5m_buy_once.mjs scripts/test_future_btc5m_extension.mjs
```

覆盖涨/跌最终按钮、默认模拟、并发去重、停止与异步取消、旧 READY 不追买、冻结证据时间、读取/存储错误、回执校验、写占用后过期或 DOM 改变，以及点击结果未知。实际平台点击及成交尚未测试。
