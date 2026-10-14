# Future BTC5m 全部买入与逐笔结算结果发布

2026-10-15 北京时间完成发布。功能提交 `3f1a98f`，发布代码提交 `69f91cedd37a830eadd651704a0bf80abfccc36c`，包含最小的应用启动修复。

## 发布范围与结果

前端已由“最近买入·最多10笔”改为全部买入记录，默认每页20笔，支持分页。后端按平台活动游标读取历史，不截取10笔；读取未完成会明示不完整并在刷新后继续。每笔按最终结算方向显示赢、亏、待结算或待确认。赢亏表示方向命中，不代表已领取或含提前卖出与手续费的已实现净收益。

候选只替换36个相关类。服务端合并校验确认89项迁移、121项依赖检查和其余JAR条目均保留。没有替换完整JAR中的其它生产补丁。

- 运行JAR：`2ac8d752ac84c9f84609f81612ce85c83691547cb9e8f56b21517a2bb0f07e7a`
- 公网页面HTML：`0542637ac28976aeec890406860de2f48bf05dab09c0f7b55c21bef3d262f58b`
- 固化镜像：`polyhermes-app:future-history-startup-20261015`，ID `sha256:1d39ebc0c48863b0acffb7e23da33e2845ee87337e42b6338d9c9aa49649d641`
- 回滚备份：`/opt/polyhermes/backups/buy-history-startup-20261015-20261014-162703`

## 验证

精确提交在干净源码目录构建成功，后端60项定向回归全部通过；同一前端产物已完成36项组件测试与构建。Flyway另与当前生产迁移清单显式比较通过89项；干净archive内缺少.git时的Gradle检查跳过，没有被当作通过依据。

应用37.959秒启动成功，重启计数0，无OOM或启动/迁移失败。app与专用relay均healthy，network namespace一致。公开HTTPS页面及JS/CSS返回成功且逐项哈希匹配；资产接口未登录返回2001，鉴权保持。

独立Bridge、MySQL容器ID及启动时间和配置哈希保持。未改数据库、钱包、登录态、自动准备或交易规则；本机助手原requestedEnabled=true、weekendOnly=false前后相同。没有升级本机助手或重载扩展。发布期间仅暂停应用重启监控，完成后已恢复active/enabled。

## 启动修复与维护记录

前次发布因运行中nginx日志写入导致未暂停的Docker commit失败并自动回滚。另一次候选启动暴露OrderPushService在@PostConstruct阶段异步查询账户，与Spring BeanFactory / Repository metrics初始化锁形成循环等待，线程栈已留证。最小修复沿用现有PositionPollingService模式，延后至ApplicationReadyEvent；真实Spring上下文行为测试在旧源码先失败，新源码再通过。其它账户筛选和连接逻辑未改。

本次脚本采用Docker暂停固化；先等app业务健康，再重启专用relay，核对app启动代次、namespace和8766实际链路。恢复监控前确认精确远端发布进程已退出。

## 浏览器验证限制

Chrome中的OKX Wallet将生产域名标为“你访问的网站存在钓鱼风险”，跳转到该扩展domain-warning.html。未点击“继续访问”，未绕过安全提示。公网产物、服务和鉴权验证完成；生产已登录页面的真实历史数量、赢亏标签与分页目视核对因此未完成，需要用户自行处理浏览器警告。此提示不被解释为已确认真实钓鱼或已确认误报。

本地证据保存在本目录：deployment-result.json、public-verification.json、clean-backend-tests.json、migration-guard-result.txt、prepared.json、local-controls-before/after.json及watchdog-maintenance-before/after.json。功能此前的真实只读集成与桌面/手机模拟验收见[功能验收](../buy-history-20261014/verification.md)。
