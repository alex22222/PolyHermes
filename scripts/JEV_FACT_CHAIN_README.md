# Jev 事实链（只读）

此模块仅研究政治/金融二元市场，排除 crypto（检查市场标题、slug、结算说明及 Gamma 市场标签）。市场类别由 Gamma 标签复核，不由来源种类决定：例如白宫文件也可能是经济类市场的官方事实。类别不在政治/金融范围、Gamma 标签不支持所选类别、或含 crypto 即停止；标签缺失或接口故障标为 `SCOPE_UNVERIFIED`，不能解释成无机会。Gamma 标签仍只是范围元数据，不替代对结算规则的人工核对。它不连接下单、Bridge、跟单或风控写入。系统页面 `/jev-fact-chain` 读取审计快照；没有快照时显示“暂无数据”，不会虚构模型结果。

## 官方来源与门禁

RSS 的 `pubDate` 必须自带明确时区；缺失时区即记为来源数据缺口，不按运行机器的本地时区推断发布时间。

第一版接受 [美联储货币政策 RSS](https://www.federalreserve.gov/feeds/feeds.htm)、[白宫 Presidential Actions](https://www.whitehouse.gov/presidential-actions/) 的文章链接，以及 [美国参议院官方投票目录](https://www.senate.gov/general/XML.htm)收录的编号投票 XML。前两者重新读取官方 RSS，确认文章 URL、发布时间和官方主机，再读取文章 HTML；只从官网标记的正文容器提取可核对文本，避免导航或页脚文字冒充证据。参议院来源只接受固定格式的 `www.senate.gov/.../vote_119_2_00241.xml` 一类单项 XML，先核对所属会期的官方目录，再交叉验证编号、日期和结果；`published_at` 对这类来源表示投票事件时间（`time_basis=vote_date`，按美国东部时区换算），不是网页首次上线时间。另记 `source_modified_at`（官网最后修改时间）及 `retrieved_at`（本系统实际抓取时间）；官网修改时间缺失、早于投票或晚于抓取均停止。送给 Jev 的证据 `observed_at` 使用实际抓取时间，绝不把投票或 RSS 发布日期伪装成系统已知该事实的时刻。目录或结果不符、来源缺失时停止；不能因确认名单暂时没有某人而推断 No。`content_sha256` 绑定用于核对的规范化文本；RSS 来源另存 `raw_html_sha256`，参议院来源另存 `raw_xml_sha256` 和目录条目哈希供审计。单次官方页面抓取上限为 2 MB，超限会停在来源错误，不产生不完整证据。导航或页脚变动不会无故使 RSS 正文规则核对失效，正文改动则必须重新核对。旧快照的 `content_sha256` 使用整页 HTML 哈希，不能直接沿用为新口径核对输入。

另支持已核实可读的 [白宫 Briefings & Statements RSS](https://www.whitehouse.gov/briefings-statements/feed/)（`source_kind=white_house_briefings`），按同一 Feed 成员、带时区日期、官网正文及哈希门禁处理，例如白宫公布法案签署的公告。它和 Presidential Actions 是不同官方目录；不在相应 Feed 中的文章不能互相冒充。白宫公告可以对应政治或金融市场，但类别仍须由 Gamma 标签核实，结算条款仍须人工逐项核对。

在调用 Jev 前，研究者须逐条填写 `rule_checks`，每项写明结算条件、当前 Gamma 或已抓取规则 PDF 的原文片段、官方事实原文片段、两者关系、核对人和核对时间；两个片段分别必须出现在抓取的规则和官方文章中。`rule_review` 同时绑定结算规则与官方文章的 SHA-256，有 PDF 时还绑定其原始文件 SHA-256，并保存证据是否符合规则及原因。只有结论为 `QUALIFIES`、逐项均为 `CONFIRMED`、且人工确认已核对市场**完整**结算说明时，才允许调用 Jev。缺失、规则或官方文章版本变化、来源日期异常时停在 `RULE_REVIEW_REQUIRED`；官网改文后即使旧引文仍在，也必须重新核对。若有明确排除条款，可在不声称已完成全部规则审查的情况下记为 `EVIDENCE_NOT_QUALIFYING`，停在 Jev 前。例如美联储 9 月 16 日加息声明被该市场的 9 月 17 日起算条款明确排除，不能当作 Yes 证据。人工核对仍可能出错，候选只表示“待复核”，不表示已结算或盈利保证。

来源类型也必须满足规则：当前白名单来源仅提供书面文章或投票 XML。若 Gamma 规则明确要求有公开录音/视频的口头提及，链路保存已抓取来源后标为 `SOURCE_TYPE_UNSUPPORTED`，即使人工表单将该文章标为符合也不得调用 Jev；有些合约还明确写明书面用词不计。未来若要支持这类市场，须先建立可核验录音/视频、发言人和发生时间的独立来源适配，再逐条审查合约附加规则；网页文字不是替代证据。

Gamma 说明若明确写着“完整/附加规则”另见外部 URL，仅支持单份位于 `polymarket-upload.s3.us-east-2.amazonaws.com/market_products/` 的 HTTPS PDF；多份完整规则文件停在 `RULE_REVIEW_REQUIRED`。只读抓取限制 2 MB、20 页，每页须能抽取文字；保存原始 PDF 与规范化逐页文本的 SHA-256、页数和抓取时间。此路径需本地 `pypdf`（`python3 -m pip install -r scripts/requirements-jev-fact-chain.txt`）；版本固定为已验证的 6.14.2，升级后可能改变抽取文本和审核哈希，须重新验证。缺依赖、链接不在白名单、扫描页无可抽取文本或抓取失败时均停在 `RULE_REVIEW_REQUIRED`。人工需打开原 PDF 逐页检查排版、图表与脚注；抽取文本不能替代视觉核对。审核 JSON 除合并规则文本哈希外，还须绑定 `rule_document_sha256`；进入 Jev 后、读盘口前再抓 PDF 校验原始文件和文本哈希。PDF 规则仍不能弥补不合格的事实来源，例如口头提及合约需要录音/视频，书面文章依旧停在 `SOURCE_TYPE_UNSUPPORTED`。其他外部规则格式尚未覆盖。

准备一份 JSON 列表，可参考 [`jev-fact-chain-input.example.json`](jev-fact-chain-input.example.json)。示例故意保留未核对状态，不能直接产生 Jev 候选。确定市场 slug、官方来源与市场原始规则后，填写完整的逐项核对记录，再运行：

```bash
python3 scripts/jev_fact_chain.py --input /absolute/path/to/reviewed-cases.json
```

也可从 `/jev-fact-chain` 页面输入市场 slug 与官方文章 URL，导出首轮观察 JSON，运行 CLI 生成来源和规则快照；再在记录详情中逐项填写条件、从官方原文摘录对应证据，并确认完整规则覆盖。页面只导出同时带规则及官方文章 SHA-256 的核对 JSON，不提交审核内容到后端，也不调用 Jev。将下载文件再次作为上面 CLI 的输入；CLI 每次重新抓取官方来源与 Gamma 规则，不接受过期的任一版本或已不在来源原文中的片段。页面审核仍需要研究者辨别规则语义和可靠性，不能由标题相似度替代。

若已找到官方文章但尚无市场 slug，可手动提供搜索词运行只读发现命令：

```bash
python3 scripts/jev_fact_chain_discover.py --source-kind federal_reserve_monetary --source-url https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm --query "Federal Reserve"
```

发现器默认按来源种类选择常见市场类别；若官方来源对应另一类 Gamma 标签，可显式指定 `--category finance` 或 `--category politics`。页面新建观察也须独立选择市场类别，最终均以 Gamma 标签和逐条结算规则复核为准。

Gamma 搜索可能返回仅含通用词的无关法案；可加 `--market-contains "Hydropower Licensing"`，要求该字面短语出现在市场问题、slug 或说明中。这只过滤搜索噪声，不代表来源与结算规则相符；过滤后 0 条也不能证明全站无相关市场。

命令先核实文章仍属于官方 feed，再从 Gamma 搜索结果中复核开放二元市场与政治/金融标签，最多追加 10 条 `discovery_basis=UNVERIFIED_KEYWORD_SEARCH` 快照。页面将“核验记录”和“关键词线索”分开；这些配对未经语义核对，不会调用 Jev 或盘口，也不能解释为已发现 edge。受保护的列表接口 `GET /api/jev-fact-chain/list` 可用 `kind=observations|discovery|all` 过滤，默认 `all` 保持旧调用兼容；页面默认展示核验记录。某个候选的 Gamma 详情/标签不可用会保留相应错误状态；搜索接口整体失败则命令返回非零码，不把数据缺口解释为没有机会。研究者仍须逐条阅读完整规则并导出审核输入，才可能进入 Jev。搜索词由操作者选择，当前不自动给来源与市场配对。

Key 从 `TYPESAFE_API_KEY` 或现有 macOS Keychain 项读取，不写入快照。默认追加到已忽略 Git 的 `data/jev-fact-chain.jsonl`。只有官方来源、完整规则确认和每项原文核对通过时才调用 Jev。模型如果不能以既定门槛确立 Yes 或 No，则停在 `JEV_INCONCLUSIVE`；确立方向后先重新读取 Gamma 市场，确认仍接单、规则和代币映射未变，再复核 Gamma 范围标签及官方来源的正文与日期版本，最后才抓该侧 CLOB 盘口。二次来源读取失败是 `SOURCE_UNAVAILABLE` 数据缺口，内容或时间变更须重新人工核对；快照和页面保留复核时间及正文哈希。市场已停单、身份变化或规则变化也在盘口前停止，审计快照保留复核时间及接单状态。报价使用刷新后的费率与地域限制，并核对盘口所属市场及 token，再按 20 份逐档深度、30 秒新鲜度、最小份数、1 美元金额和 Gamma 当前费率复核。盘口未明确启用、费用承担方式不明或盘口身份不符时停在 `QUOTE_UNAVAILABLE`。`restricted` 为真或未知时仍可保留只读报价，但状态为 `RESTRICTION_UNVERIFIED`，不生成候选；该字段表示某些地域受限，不能用公开盘口证明当前账户可交易。结果仅供 Shadow 审查，单位价差是“若该侧兑付 $1”的情景值，不是预期收益或可成交利润。页面所示盘口只是抓取当时的历史快照，查看时不能当成当前可执行报价；全部输入被跳过时 CLI 返回非零退出码。

进入 Jev 时，快照还保存实际提交的 `jev_evidence`（官方 URL、标题、带时间口径的发布时间或投票时间、可选官网修改时间、系统观测时间和事实文本），页面第 3 阶段与模型版本及三项分数一同展示，便于回查模型真正看到的事实与时间。RSS 文章只送人工确认的引文；简短且已核验目录身份的参议院投票送完整结构化文本，以保留人名、职位、投票问题与结果的上下文。API Key 不属于该证据包；未通过前置核对的记录不会生成它。

本地后端默认从仓库根目录 `data/jev-fact-chain.jsonl` 读取。容器可选用仓库根目录的 `docker-compose.jev-fact-chain.yml` 作为附加 Compose 文件：它只将一个已有快照文件以只读方式挂到 `/app/jev-fact-chain.jsonl`，并设置 `JEV_FACT_CHAIN_SNAPSHOT_PATH`。默认来源是 `./data/jev-fact-chain.jsonl`；服务器若使用其他路径，需在 Compose 启动环境设置 `JEV_FACT_CHAIN_SNAPSHOT_FILE` 为该文件的绝对路径，确保容器用户可读。文件不存在会直接报错，不会创建空目录。使用前可运行 `docker compose -f docker-compose.prod.yml -f docker-compose.jev-fact-chain.yml config --quiet` 校验合并配置；这里仅准备了可选配置，尚未启用或部署，线上页面仍可能显示暂无快照。

验证：

```bash
python3 -m unittest scripts/test_jev_fact_chain.py scripts/test_jev_fact_chain_discover.py scripts/test_jev_shadow_probe.py scripts/test_jev_shadow_monitor.py
```
