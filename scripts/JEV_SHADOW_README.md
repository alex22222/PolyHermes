# Jev Shadow 初验

这是独立的只读 CLI，不连接后端下单、Bridge、跟单配置或钱包。它只检查人工提供过证据的市场，不会凭市场标题自动给未来事件预测胜率，也不会自动发现全站所有市场。

## 输入与运行

参考 [`jev-shadow-input.example.json`](jev-shadow-input.example.json) 准备 JSON 列表。`market_slug` 必须是**市场** slug，不是 event slug；每条证据要有 HTTPS 来源、UTC 时间和当时可见的简短内容。操作者负责核验来源真实性以及该来源是否符合市场结算规则；程序不会抓取来源网页。

推荐先在 TypeSafe 后台轮换已贴到聊天中的 Key，再将新 Key 安全保存到 macOS Keychain（终端会提示输入，输入内容不会显示）：

```bash
security add-generic-password -U -a typesafe -s polyhermes-jev-shadow -w
```

脚本优先读取 `TYPESAFE_API_KEY` 环境变量；该变量未设置时，在 macOS 上读取上述 Keychain 条目。Key 不会写入输入文件、输出文件或仓库。先验证 Jev API 连通性：

```bash
python3 scripts/jev_shadow_probe.py --check-jev
```

连通性验证成功后，运行市场扫描：

```bash
python3 scripts/jev_shadow_probe.py --input /absolute/path/to/evidence.json
```

默认追加到 `data/jev-shadow.jsonl`（已忽略 Git）。也可用 `--output` 指定位置、`--shares` 调整模拟份额、`--min-gap` 调整“若该侧胜出时”的最低单位净兑付差；默认分别为 20 份与 0.15。以上都不是交易参数或盈利保证。

## 输出含义

- `REVIEW_CANDIDATE`：Jev 对某一结果已被证据确立的判断 ≥0.95，对反面和歧义的判断均 ≤0.05，且对应侧盘口深度、时效、最小单量和费用通过，单位净兑付差达到阈值。仍须人工复核证据与结算规则。
- `NO_CANDIDATE`：至少有一侧可报价，但未满足判断或价格门槛。
- `NO_ACTIONABLE_QUOTE`：两侧均无法按指定份额形成可用报价。
- `SKIPPED`：市场、证据、API 或费用信息不满足初验条件。

`--check-jev` 只向 TypeSafe 发送一个固定文本的 Noul 请求，不访问市场、不读取盘口，也不连接任何下单功能。

如果本次没有任何市场完成 Jev 判断，CLI 返回非零状态；每个状态仍会追加到快照，方便定位原因。

单位净兑付差是**假设买入侧最终兑付 1 美元时**的账面上限，不是 Jev 事件胜率、预期收益、成交承诺或可交易 edge。脚本对订单簿逐档计算买入 VWAP；费用仅支持 Gamma 明确返回的 `feesEnabled=false` 或 `feeSchedule.exponent=1`，其他情况保守跳过。最小份数按盘口 `min_order_size` 校验，市价买入金额另按 1 美元门槛校验。盘口超过 30 秒、深度不足、市场未接受订单或非二元 Yes/No 市场也跳过。输出保留证据、规则、模型版本、盘口哈希和实际使用档位，供前瞻复核；不会保存 API Key。

验证命令：

```bash
python3 -m unittest scripts/test_jev_shadow_probe.py
```

当前这只是接入与候选筛选的离线验证模块。要评价 Jev 是否真的提高收益，还需在独立前瞻样本中验证来源准确性、模型判断准确性、实际可成交性以及扣费后结果，并与同期盘口基线比较。

## 72 小时观察

`jev_shadow_monitor.py` 每次读取 Gamma 按 24 小时成交量排序的前 300 个活跃市场，只扫描标题或 slug 命中政治/金融关键词、且未命中 crypto 关键词的 Yes/No 市场。这是关键词筛选，不是全站覆盖或官方分类。它用 20 份逐档买入价、Gamma 费用、最小份数、1 美元买入门槛和 30 秒盘口时效计算双边配对成本；结果追加到已忽略 Git 的 `data/jev-shadow-monitor.jsonl`。同一个六小时时段和脚本版本只保存一条快照；新口径使用 `schema_version=5`，此前含 crypto 的 `schema_version=4` 快照保留但不与新口径混合统计。

```bash
python3 scripts/jev_shadow_monitor.py --until 2026-09-27T00:15:00+00:00
```

这个监测只筛选配对价差，不自动把市场标题当作事件证据。若找到带日期的可靠结算证据，再用上面的 `jev_shadow_probe.py` 对对应市场进行 Jev 判读；没有证据时记录为未评估，而不是给它虚构胜率。若一轮没有可用的双边报价，命令返回非零状态，表示数据缺口，不能写成“无 edge”。
