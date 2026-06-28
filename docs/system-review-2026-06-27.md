# PolyHermes 系统审视与点评

> 生成时间：2026-06-27  
> 审视范围：后端（Kotlin/Spring Boot）、前端（React/TS/Vite）、Bridge（Python/FastAPI + Playwright）、数据库与运维

---

## 一、稳定性：生产环境像「临时展台」

### 1. 后端服务频繁掉线

今天已经两次发现「后端服务没了」。一个生产服务被一次 HTTP 长请求（leader scan）就打到消失，说明不是健壮性问题就是资源管理问题。

更讽刺的是：服务没了之后我们甚至看不到 `actuator/health`，连个健康检查端点都没有。

### 2. OOM / 阻塞式 HTTP 是大概率死因

`LeaderScannerService.scan()` 是**同步阻塞**的，4 个类别串行 `discover` + `analyze` + `persist`，内部还调 Data API，直接跑在 Tomcat 线程上。

用 curl 调用 `/scan/run`，客户端超时 120s，服务端 scan 还在跑，连接断开、请求堆积、最终把 JVM 压垮——这几乎就是单机压测自杀。

### 3. 配置管理业余

`.env` 通过 `source` 不能把 `DB_PASSWORD` 传给 Java，结果现在启动脚本里**硬编码密码**。

更离谱的是 `application.properties` 默认连 `localhost:3306`，而实际 MySQL 在 `3307`，完全靠启动时环境变量续命。这种配置早晚再坑一次。

---

## 二、数据与业务：「看起来有数据」比「数据正确」更重要？

### 4. 历史订单之前是在「造假」

在没加 `wallet_address` 精确匹配前，多个 Bridge 只读账户会显示同一组仓位；BUY 列表里 `failed` 和 `filled` 混在一起。

这说明系统长期把「有数据展示」当成「展示正确数据」。修复手段也是补丁式：加字段、清数据、改过滤，而不是反思数据模型为什么从一开始就没把账户隔离做好。

### 5. Bridge 持仓 = 当前登录账户的持仓

系统里有多个 Bridge 只读账户（zhangmin、kimi），但 Bridge 只能同时登录一个 Polymtrade 钱包。

结果加了精确匹配后，其他账户直接显示为空——数据是对了，但业务上只剩半个功能。多账户架构从根上就是「一个浏览器 session 硬撑多个账户」。

### 6. 加密密钥一致性崩溃

日志里大量：

```
BadPaddingException: Given final block not properly padded
```

私钥和 API Secret 解密失败。这意味着：要么加密密钥换了但历史数据没迁移，要么不同环境用了不同 key，要么加密逻辑本身有 bug。无论哪个，都是**生产数据完整性事故**。

---

## 三、Bridge：与后端的契约像「各说各话」

### 7. Bridge API 404 满天飞

后端调用 Bridge `/status`、 `/portfolio` 返回 404，但 Bridge 明明在跑。

根因：Bridge 实际监听的是 8080，但 `/` 返回 HTML，说明端口可能被其他服务占用，或者 FastAPI 路由没按预期注册。更可能是**启动了多个 Bridge 或旧实例没清**。

### 8. Bridge 端口号都没对齐

后端配置文件 `application.properties` 里写死 `http://localhost:8080/...`，但 `.env` 里没有端口配置，`main.py` 里才写死 `8080`。

一个微服务间通信的端口靠「两边各写死一个数」来约定，这已经是 2010 年前的做法。

---

## 四、代码与工程：补丁摞补丁

### 9. Flyway 迁移被当橡皮泥

已经应用的 V63 被改了，结果 checksum mismatch，只能手动删 `flyway_schema_history` 里的记录重新跑。

这是 Flyway 使用的典型反模式：改已发布迁移。下次再改 V63/V64/V65，数据库历史记录还是一团泥。

### 10. 一次 commit 47 个文件

最近一个 commit 改了 47 个文件，涉及后端、前端、Bridge、数据库迁移、测试。

这不是一个「功能提交」，这是一个「我不知道这些改动有没有耦合所以全推上去」提交。回滚时几乎不可能精准定位。

### 11. 类型与空值处理敷衍

前端脚本里 `p.get('marketTitle','')[:60]` 在 JSON 值为 `null` 时仍然报错，因为 `dict.get` 的默认值只在 key 不存在时生效。

一个 TypeScript 前端 + Kotlin 后端的项目，在边界空值上反复栽跟头，说明类型系统只是摆设。

---

## 五、运维与可观测：瞎子摸象

### 12. 没有健康检查、没有 metrics

`/actuator/health` 404，没有 Prometheus，没有 metrics。

服务死没死只能靠 `curl` 登录接口猜，靠 `pgrep` 找进程。这在生产环境是不可接受的。

### 13. 日志里全是噪音

解密失败、WebSocket EOF、Bridge 404、WCOL 跳过……这些错误要么没处理，要么处理方式是「打一行 warn 继续跑」。

当错误日志变成背景噪音，真正的故障信号就会被淹没。

---

## 六、最犀利的总结

这个系统目前的状态是：**功能列表很长，但每一个功能都在靠补丁和运气支撑。**

- 想看仓位？只能看当前登录那个钱包，其他账户 correct-but-empty。
- 想看历史订单？之前看的是混合物，现在才对了一半。
- 想跑 leader 扫描？服务可能会被你跑挂。
- 想重启服务？先手动 export 硬编码密码。
- 想保证数据安全？加密密钥已经不匹配了。

**最核心的问题不是某个 bug，而是：系统把「能跑起来」当成「可以上线」，把「页面有数据」当成「业务正确」。**

---

## 建议优先级

| 优先级 | 事项 |
|--------|------|
| P0 | 把 leader scan 改成异步任务（Spring `@Async` / 任务表），禁止阻塞 HTTP 线程 |
| P0 | 解决加密密钥不一致问题，统一密钥管理或重加密历史数据 |
| P1 | 配置外部化（Spring Cloud Config / 至少 ENV 文件），去掉硬编码密码 |
| P1 | 启用 actuator health + metrics，加进程监控（systemd/supervisor） |
| P1 | 修复 Bridge 多实例/端口占用，明确后端↔Bridge 契约 |
| P2 | Flyway 迁移锁定，已发布版本不再修改 |
| P2 | 提交粒度拆分，前端/后端/Bridge/DB 分开 commit |
| P2 | 补全空值边界测试，尤其是 Bridge 返回 null 的字段 |

---

> 下一步行动建议：先治 **P0 的扫描阻塞 + 加密密钥**，这两个是能让系统再次暴雷的命门。
