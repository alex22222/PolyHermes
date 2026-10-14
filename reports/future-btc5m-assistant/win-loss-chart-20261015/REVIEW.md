# Future BTC5m 赢亏比例图发布

2026-10-15 北京时间发布完成，代码提交 `5545fb3d7178bd31c9e707751bd3c7d1ef6f440b`，仅更新前端。

## 展示口径

在全部买入记录上方显示绿赢、红亏环形图及已结算胜率。按全部已加载买入笔数计算 `WIN / (WIN + LOSS)`，同轮多笔分别计数，不受表格翻页影响。待结算与待确认单列笔数，不计入胜率；无已结算记录显示中性空环和“—”。历史未完整加载时标注当前统计范围；数据过期、缺失或读取失败时隐藏旧图表。沿用现有资产刷新，不新增接口请求或修改交易控制。

## 验证结果

- 41项相关前端测试全部通过；新增5组行为回归先失败再通过。
- 精确提交在干净前端源码目录构建成功，没有将工作区其它未提交页面打入发布包。无新增依赖；保留构建既有大包提示。
- 使用真实React组件和隔离mock API核对桌面、390px手机、部分历史、空记录。手机文档宽390px，无横向页面溢出。新增文字对比度5.34至6.71。
- 公网页面、JS/CSS均返回成功且哈希与精确产物相符；16个静态文件在服务端逐一校验。资产接口未登录仍返回2001。
- 全部四个容器ID、启动时间、重启计数保持；后端JAR、配置哈希和监控active/enabled保持。本机requestedEnabled=true、weekendOnly=false前后相同。没有重启服务、改动后端、执行数据库修改或触发交易控制。

## 产物与恢复

- HTML SHA256：`fa939d75b46ee9545ead6a6703d60a0ca42521e0ed87c9115c0ab2cff022833c`
- 保留的最新后端JAR SHA256：`047842624809a76a1c4cbd0520cb5c6f82fddce698d81522d61801448df97af5`
- 固化镜像：`polyhermes-app:win-loss-chart-5545fb3`，`sha256:295b6fa291bc608cf10ff16b37323662387e7b9d1f542fe268ce9d6db561568d`
- VPS前端备份：`/opt/polyhermes/backups/win-loss-chart-5545fb3-20261014-171039`

先上传静态资源、最后切换index，旧资源保留。首轮在Docker暂停固化后立即判断健康状态，过早触发前端回退；确认服务健康、未重启及旧页面恢复后，改为90秒内等待相同启动身份恢复健康，再重试成功。未修改监控设置。

服务器另一轮后端维护在本次发布前完成，已以维护后最新JAR为基线，未覆盖该修复。生产验证为公共产物、服务、鉴权与保护项；未把本地模拟图当作真实钱包统计，也未绕过此前Chrome OKX Wallet域名警告进行生产登录页目视核对。

## 界面预览

下图为模拟数据：18赢、6亏、13待结算、8待确认，胜率75%。不代表当前钱包真实统计。

![桌面与手机预览](desktop-mobile-preview.jpg)

本地证据：`final-tests.log`、`clean-frontend-build.log`、`visual-qa.json`、`deployment-result.json`、`public-verification.json`、`production-before.json`、`local-controls-before/after.json`。运行日志和构建产物未提交。
