# Future 策略迁移到 2019 Intel Mac：开机部署清单

准备日期：2026-10-17。迁移的是当前 Future BTC 助手；服务器上的项目网页、后端、数据库和原 Polymtrade Bridge 留在原处。

推荐先迁移当前 **15 分钟反 1 小时方向**；同一个安装包也支持切回 **5 分钟热门方向**，一次运行一种策略。安装包固定当前源码与扩展 0.7.3，自动买入默认关闭。

## 已准备的东西

- `install.command` / `install.py`：校验文件哈希、Intel/macOS/Python、端口，创建原生虚拟环境，生成新机专用服务配置；不启动交易。
- `manage.command` / `manage.py`：环境检查、只读观察启动、新 SSH key、旧机停用交接、历史归档、新机启动、停止。
- `app/scripts/`：当前助手四个 Python 模块、依赖文件、隧道和完整 Chrome 扩展，包含 `renderer.js`。
- `vendor/`：官方 Python 3.13.16 安装包、Google Chrome Universal 安装镜像及三份已固定版本的通用 Python wheel（含 Python 3.10 条件依赖）；安装依赖不需要 Homebrew、编译器或在线 pip。
- `profile.json`：当前选择 `btc15m_counter_1h`、金额 `$1`、`weekendOnly=false`；原机仍运行时采集的配置，不能当作停机凭证。
- `BUNDLE-MANIFEST.json`：文件 SHA256 和来源哈希。包内没有浏览器登录资料、钱包、SSH 私钥、数据库或原机 ARM 虚拟环境。

## 第一步：闲置电脑开机后

1. 接通电源、联网并登录 macOS 用户。检查“关于本机”：要求 **macOS 13 或更新**；2019 MacBook Pro 可使用受支持的 macOS 版本。若系统仍旧，应先升级，再部署。
2. 把整个 ZIP 用 AirDrop 或 U 盘传过去，解压到“下载”等本机目录；不要在 iCloud 同步目录或 ZIP 预览里直接运行。
3. 已有可用 Python 3.10+ 和 Chrome 可以复用；缺少时双击 `vendor/python-3.13.16-macos11.pkg` 完成官方安装，打开 `vendor/googlechrome.dmg` 把 Chrome 拖到“应用程序”。系统安装提示由你完成。
4. 如仍需代理，在新机安装你使用的代理客户端并自行导入配置。当前配置是 HTTP/SOCKS 共用 `127.0.0.1:7890`；仅复制代理应用不等于配置已经迁移。代理订阅、密码和网络账户不在迁移包中。
5. 双击 `install.command`，先看到只读预检和具体阻断原因。然后在该解压目录的终端执行：

```bash
bash ./install.command --install
```

代理端口不同就明确指定；新机实测直连可访问所有行情源时才使用直连：

```bash
bash ./install.command --install --proxy-http http://127.0.0.1:7897 --proxy-socks 127.0.0.1:7897
# 或者
bash ./install.command --install --direct
```

默认安装到 `~/Library/Application Support/PolyHermesFuture`。安装完成保留两处 STOP，两个 LaunchAgent 仅生成到安装目录，尚未接入登录自启。反复执行相同安装会检查已有安装，保留状态；不同版本或非空未知目录会拒绝覆盖。

## 第二步：新机先验收，不接管旧机

在终端设置本次任务变量，后续命令可直接复制：

```bash
FUTURE_MAC_ROOT="$HOME/Library/Application Support/PolyHermesFuture"
bash "$FUTURE_MAC_ROOT/manage.command" doctor
bash "$FUTURE_MAC_ROOT/manage.command" generate-key
bash "$FUTURE_MAC_ROOT/manage.command" start-observe
```

`generate-key` 只生成新机专用 SSH key，输出公钥。把这个公钥交给现有服务器管理员完成授权；**不能把公钥输出当成授权成功**。不复制原机 `~/.ssh/polymtrade_vultr_ed25519` 私钥。包内提供的服务器已知公钥用于固定服务器身份：

```text
107.191.42.75 ED25519 SHA256:1+Ty+dXD/c6AqAaMLcjEA/RzBdjHGTy2u/E9pbiVlBA
```

使用当前账户新建/授权专用 key 后，新机先做只读登录检查。默认代理示例：

```bash
ssh -T -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$FUTURE_MAC_ROOT/ssh/known_hosts" \
  -o 'ProxyCommand=nc -X 5 -x 127.0.0.1:7890 %h %p' \
  -i "$FUTURE_MAC_ROOT/ssh/id_ed25519" root@107.191.42.75 true
```

直连模式去掉 `ProxyCommand`；修改过代理端口则使用实际端口。服务器授权操作尚未执行，需新机开机生成公钥后完成。

打开 Chrome 并手动登录 Future。同一个 Future 账户正常登录，不导入浏览器 Profile、Cookie、钱包或 Keychain。打开 `chrome://extensions`，开启开发者模式，“加载已解压的扩展程序”选择：

```text
~/Library/Application Support/PolyHermesFuture/app/scripts/future-btc5m-extension
```

在选择文件夹窗口可用 `Command+Shift+G` 粘贴路径。核对版本 0.7.3；新机安装时需由你确认 Chrome 的 `power`、`debugger` 权限提示。打开当前策略对应的 Future BTC 页面，保持完整票据和仓位列表可见。

`start-observe` 只启动新机助手并保留 STOP，不启动连接生产项目的隧道。此时旧机可以继续运行；新机页面应显示停止/关闭状态。`doctor` 只读检查依赖、证书、时区、Chrome、代理、服务归属与页面报告；`effectiveEnabled=false` 或 `executorReady=false` 不能代替真正的关闭证明。

## 第三步：停旧机、交接，再启新机

**这一步现在不执行。只有新机安装、登录、代理及 SSH 授权均完成后再执行。**

先在旧机扩展详情确认审计队列已经全部写入本机账本。未发送的审计保留在旧 Chrome 中，不删除、不伪造成成交；本工具不会导出浏览器存储。

在旧机、迁移包解压目录中执行（保留真实旧机路径）：

```bash
python3 ./manage.py handoff-source \
  --source-root /Users/henry/projects/polyhermes \
  --source-state /Users/henry/projects/polyhermes/reports/future-btc5m-assistant \
  --output "$HOME/Desktop/Future-source-handoff" \
  --confirm-source-cutover
```

该显式命令会先关闭旧机自动准备并回读确认，写入 STOP，停用并卸载旧机助手/隧道两个 KeepAlive LaunchAgent，确认 8766/8767 连续六秒无监听，再生成停机凭证和最终账本快照。它不退出钱包、不撤单、不卖出持仓，也不删除旧数据。完成后关闭旧 Future 标签页或禁用旧扩展，避免今后误启。

只有命令完整成功并生成 `receipt.json` 才可交接。若报错，旧机可能已经安全停止；检查错误和 STOP/服务状态，不手动补造 receipt，不跳过停用验证。

把整个 `Future-source-handoff` 文件夹通过 AirDrop/U 盘传到新机。它含真实交易审计，按个人资料保管。在新机执行：

```bash
bash "$FUTURE_MAC_ROOT/manage.command" accept-handoff "$HOME/Desktop/Future-source-handoff"
bash "$FUTURE_MAC_ROOT/manage.command" start-target
bash "$FUTURE_MAC_ROOT/manage.command" doctor
```

源机凭证规定最早启动时间为**停机后的下一个完整 15 分钟轮次再加 1 秒**；早于这个时间会拒绝，稍后重跑即可。即使选择 5 分钟策略也使用这个保守交接边界。脚本不会睡到边界后自行开启交易。

历史账本验证哈希后只归档到新机 `history/`，不会重放旧任务、未完成票据或订单，也不会把旧 `status.json` 当作新机状态。新机助手的任务/点击账本从新的自然轮次开始，完整旧账本保留在归档和旧机；同钱包的平台资产与买入历史仍按现有公开查询读取。

`start-target` 会核对新机配置与交接策略一致（不一致则拒绝），恢复周末设置，启动新机助手和专用隧道，**自动买入仍关闭**。隧道必须拒绝覆盖活动远端 socket；如提示旧 socket 仍活动，检查旧机确实停用，不强制抢占或修改服务器 socket。启动成功仍需验证项目网页已经连到新机，而不能仅看 SSH/launchd 进程存在。

在原有项目控制页验收：

- 桥在线，金额 `$1`，策略/周期与交接配置一致；`requestedEnabled=false` 且 `preparation.enabled=false`。
- 新 Chrome 页面报告持续新鲜：`preflight.checkedAt` 与 `receivedAt` 均不超过 5 秒；页面标题、轮次、方向按钮和美元买入栏正确。
- Chainlink feed 为 `CURRENT`；Gamma、开盘参考价、15 分钟与 1 小时盘口在自然窗口按现有规则读取。网络失败如实阻断，不补买。
- 周末开关与旧机一致。本次快照为 `weekendOnly=false`，不是默认仅周末；重启助手后该项可能恢复默认 `true`，需重新核对配置。
- SSH 公钥已授权、生产 relay 查询成功；当前旧机两个 LaunchAgent 仍 disabled，旧 Future 页面/扩展已停止。

全部通过后，由你在项目页开启现有“自动准备票据”。从下一个符合条件的自然窗口开始观察，不强制生成信号，不测试性补单。出现成交时以平台记录、页面持仓核实及实际份额/均价为准；点击与成交、结算仍分别记录。

## 规则与运行条件

| 项目 | 5 分钟 | 15 分钟（当前） |
|---|---|---|
| 策略 | `btc5m_favorite` | `btc15m_counter_1h` |
| 入场窗口 | 第 60–80 秒 | 第 150–170 秒 |
| 方向 | 按钮较高的一方 | 同左，且与同期 1 小时热门方向相反 |
| 金额/次数 | `$1`，每轮最多一次 | 同左 |
| 价格 | 60–97¢；准备价 ±5¢；页面/盘口差 ≤3¢ | 同左 |

保持接电、网络、用户登录会话和 Chrome；关闭浏览器、退出登录、系统睡眠或合盖都不能保证运行。现有 0.7.3 包含锁屏渲染保活，但 Intel 真机锁屏验收尚未进行；先在前台稳定运行，再在自动买入关闭时做 10–20 分钟锁屏/恢复检查，核对页面报告和自然轮次。不能用本机 ARM 测试替代 Intel 实机验收。不要关闭 FileVault、设置自动登录或放宽 Chrome/系统安全设置来省略启动步骤。

## 停止与回退

```bash
bash "$FUTURE_MAC_ROOT/manage.command" stop-target
```

新机关闭并确认两端口停止后，才考虑恢复旧机。旧机两个 LaunchAgent 需明确重新启用并 bootstrap；保留 STOP 与买入关闭，先做只读检查，再按新轮次人工切回。不要同时启用两台机器；单个 VPS socket 只防隧道竞争，不能提供跨电脑账户交易去重。

## 本次预备验收与资料

部署工具测试使用临时目录和模拟服务管理，检查离线安装、目标路径、默认关闭、双机交接门槛及失败拒绝；没有停止当前源机或发真实订单。目标机现仍关机，登录、自启、网络、自然轮次与锁屏需要开机后验收。

官方兼容资料：[Chrome 系统要求](https://support.google.com/chrome/a/answer/7100626?hl=en)、[Python 3.13.16](https://www.python.org/downloads/release/python-31316/)、[Apple：Sequoia 兼容机型](https://support.apple.com/en-us/120282)。
