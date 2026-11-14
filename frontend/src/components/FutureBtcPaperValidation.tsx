import { Alert, Card, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { BtcForwardPaperRow, BtcLegacyPaperRow, BtcPaperStats, BtcPaperValidationStatus } from '../types/futurePaperObserver'

const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const money = (value: number | null | undefined) => value == null ? '—' : `${value < 0 ? '-' : '+'}$${Math.abs(value).toFixed(2)}`
const time = (value: number | null) => value == null ? '—' : new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
const cents = (value: number) => `${value.toFixed(0)}¢`
const direction = (value: string) => <Tag color={value === 'Up' ? 'green' : 'red'}>{value === 'Up' ? '涨' : '跌'}</Tag>
const result = (value: boolean | null) => value == null ? <Tag>待结算</Tag> : <Tag color={value ? 'green' : 'red'}>{value ? '赢' : '亏'}</Tag>
const ruleNames: Record<string, string> = {
  BASELINE: '完整入场基线', G1: 'G1 · |1小时趋势|≥15bp', G2: 'G2 · 避开5–15bp',
  A: '候选 A · G2 + 波动≤3bp/分钟', B: '候选 B · G2 + 入场方向确认',
}
const reasons: Record<string, string> = {
  WAITING_ENTRY_WINDOW: '等待本轮入场窗口', ENTRY_WINDOW_CLOSED: '本轮入场窗口已结束',
  OUTSIDE_ENTRY_WINDOW: '不在150–170秒入场窗口', R1_HIGH_VOLATILITY: 'R1波动超过门槛，本轮跳过',
  SAME_AS_1H: '与1小时同向，本轮跳过', PAPER_PREPARED: '已记录纸上准备快照，等待二次核验',
  PAPER_RECORDED: '已记录通过核验的纸上单', PAPER_VERIFIED: '已记录通过核验的纸上单',
  PRICE_GATE: '准备价或可成交价不在60–97¢', PRICE_DRIFT_5C: '价格偏离准备快照超过±5¢',
  MARKET_QUOTE_MISMATCH: '页面与盘口价格不一致', BOOK_STALE: '盘口已过期，等待新报价',
  BROWSER_NOT_CONNECTED: 'Future页面报告已过期或未连接', SIGNAL_NOT_FRESH: 'Chainlink采样已过期',
  BRIDGE_UNAVAILABLE: '助手只读连接暂不可用', INSUFFICIENT_PAPER_DEPTH: '盘口深度不足，不能模拟成交',
  ENTRY_BEFORE_ENROLLMENT: '入场窗口早于本次启用时间，本轮跳过', BRIDGE_NOT_CURRENT: '助手轮次或时钟尚未对齐',
  MISSING_ENTRY_EVIDENCE: '入场证据不完整，继续等待', CHAINLINK_BASELINE_UNVERIFIED: 'Chainlink结算基准或行情尚未核实',
  CHAINLINK_BASELINE_CHANGED: '两次读取的Chainlink结算基准不一致，本轮跳过',
  WRONG_MARKET_PRICE_CONFIG: 'BTC市场结算配置不匹配', MARKET_TIMEZONE_MISSING: '市场时间缺少时区信息',
  CHAINLINK_DIRECTION_INVALID: 'Chainlink方向数据不一致，继续等待', FUTURE_TICKET_UNVERIFIED: 'Future页面票据或更新时间未通过核验',
  FUTURE_QUOTES_UNVERIFIED: 'Future页面报价缺失或持平', FUTURE_SELECTED_SIDE_MISMATCH: 'Future页面选中方向不一致',
  FUTURE_SNAPSHOT_REGRESSED: 'Future页面快照时间异常，等待新报告', R1_OR_FEATURES_UNVERIFIED: '波动超限或入场行情尚未核实',
  MARKET_INPUTS_UNVERIFIED: '市场配置尚未核实', BOOK_IDENTITY_MISMATCH: '盘口与目标市场不匹配',
  BOOK_TIME_INVALID: '盘口时间无效', INVALID_BOOK: '盘口数据尚未核实', INVALID_BOOK_LEVEL: '盘口档位数据尚未核实',
  TIED_QUOTES: '盘口报价持平，继续等待', FAVORITE_CHANGED: '热门方向已变化，本轮等待或跳过',
  FUTURE_CLOB_GAP_3C: '页面与盘口价差超过3¢', PAPER_PREPARATION_EXPIRED: '纸上准备快照已过期，本轮跳过',
  MARKET_NOT_UNIQUE: '目标市场无法唯一确认', MARKET_NOT_ACTIVE_OR_WRONG_ROUND: '市场未开放或轮次不匹配',
  INVALID_TOKENS: '市场结果标识尚未核实', FEE_UNVERIFIED: '市场费率尚未核实',
  RESOLUTION_UNVERIFIED: '平台最终结果尚未核实', RESOLUTION_IDENTITY_MISMATCH: '结算结果与目标市场不匹配',
  PAYOUT_UNVERIFIED: '平台最终兑付尚未核实',
}

function Stats({ stats, label, forward = false }: { stats: BtcPaperStats, label: string, forward?: boolean }) {
  return <Space direction="vertical" size={4} style={{ maxWidth: 300 }}>
    <Typography.Text strong>{label}</Typography.Text>
    <Typography.Text>纸上单 {stats.trades} 笔 · 已结算 {stats.settled} 笔 · 待结算 {stats.pending} 笔</Typography.Text>
    <Typography.Text>胜率 {percent(stats.winRate)}（赢 {stats.wins} / 亏 {stats.losses}）</Typography.Text>
    <Typography.Text strong>模型净盈亏 {money(stats.netPnlUsd)}</Typography.Text>
    {forward ? <>
      <Typography.Text>单位本金收益 {percent(stats.roiPerDollar)}</Typography.Text>
      <Typography.Text type="secondary">额外成本1¢后 {money(stats.netPnlWithExtraCentUsd)}</Typography.Text>
      <Typography.Text type="secondary">不利成交价1¢后 {money(stats.netPnlWithAdverseCentUsd)}（深度已核实 {stats.adverseCentVerifiedTrades ?? 0} / {stats.settled}）</Typography.Text>
    </> : <Typography.Text type="secondary">模型费率已核实 {stats.feeVerifiedSettled ?? 0} / {stats.settled} 笔结算单</Typography.Text>}
    {stats.rule !== 'BASELINE' ? <Typography.Text type="secondary">过滤亏单 {stats.filteredLosses ?? 0} · 同时过滤赢家 {stats.filteredWins ?? 0}</Typography.Text> : null}
  </Space>
}

const forwardColumns: ColumnsType<BtcForwardPaperRow> = [
  { title: '轮次开始', dataIndex: 'periodStart', width: 170, render: time },
  { title: '方向', dataIndex: 'side', width: 70, render: direction },
  { title: '模拟均价', dataIndex: 'priceCents', width: 90, render: cents },
  ...['G1', 'G2', 'A', 'B'].map(rule => ({ title: `${rule} 合格`, key: rule, dataIndex: 'rules', width: 90,
    render: (rules: string[]) => rules.includes(rule) ? <Tag color={rule === 'G1' ? 'processing' : 'warning'}>合格</Tag> : <Tag>过滤</Tag> })),
  { title: '波动', dataIndex: 'volatilityBp', width: 90, render: (value: number) => `${value.toFixed(2)}bp` },
  { title: '顺向偏移', dataIndex: 'signedDistanceBp', width: 100, render: (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}bp` },
  { title: '平台结果', dataIndex: 'win', width: 90, render: result, sorter: (a, b) => Number(a.win ?? -1) - Number(b.win ?? -1) },
  { title: '模型净盈亏', dataIndex: 'netPnlUsd', width: 110, render: money },
]
const legacyColumns: ColumnsType<BtcLegacyPaperRow> = [
  { title: '轮次开始', dataIndex: 'periodStart', width: 170, render: time },
  { title: '方向', dataIndex: 'side', width: 70, render: direction },
  { title: '准备价', dataIndex: 'priceCents', width: 80, render: cents },
  { title: '原估算结果', dataIndex: 'originalWin', width: 100, render: result },
  { title: '平台结果', dataIndex: 'correctedWin', width: 100, render: result,
    sorter: (a, b) => Number(a.correctedWin ?? -1) - Number(b.correctedWin ?? -1) },
  { title: '结果核对', dataIndex: 'mismatch', width: 100,
    render: (value: boolean | null) => value == null ? '—' : value ? <Tag color="orange">已校正</Tag> : <Tag>一致</Tag> },
  { title: '模型净盈亏', dataIndex: 'netPnlUsd', width: 110, render: money },
  { title: '费率读取时间', dataIndex: 'feesFetchedAt', width: 170, render: time },
]

export default function FutureBtcPaperValidation({ data, error }: { data: BtcPaperValidationStatus | null, error: string | null }) {
  const forward = data?.forward
  const legacy = data?.legacy
  return <Space direction="vertical" size="large" style={{ width: '100%' }}>
    <Card title="BTC 策略前瞻验证 · 基线 / G1 / G2 / A / B">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Tag color="blue">只做纸上验证 · 每笔模拟本金 $1 · 不调整实盘规则</Tag>
        <Typography.Text type="secondary">先记录纸上准备快照，再只读核验：150–170秒入场、R1波动门槛、反1小时方向、60–97¢、页面与盘口差≤3¢、准备价浮动±5¢及$1盘口深度。核验通过才计入以下成绩；不是实际成交。</Typography.Text>
        <Typography.Text type="secondary">候选 A：G2 + 波动≤3bp/分钟。候选 B：G2 + Chainlink现价相对60秒TWAP开盘基准，向下注方向偏移。基线、G1、G2同期对照。</Typography.Text>
        <Typography.Text type="secondary">以平台最终兑付为准，逐档模拟市场手续费；另列每笔1¢额外成本、成交价不利1¢压力结果，均不是实盘收益。</Typography.Text>
        {error || !forward?.fresh ? <Alert type="warning" showIcon message="BTC 前瞻采样状态待核实"
          description={error || '等待独立采集器的新鲜报告，尚无样本不代表零收益。'} /> : <>
          <Typography.Text type="secondary">前瞻起点：{time(forward.startedAt)} · 规则冻结：{time(forward.rulesFrozenAt)} · 采集更新：{time(forward.heartbeat)}</Typography.Text>
          <Typography.Text>准备信号 {forward.signalCount} 笔 · 已通过完整核验 {forward.baseline.trades} 笔</Typography.Text>
          <Typography.Text type="secondary">{forward.latest ? reasons[forward.latest.reason] || '本轮所需数据尚未核实，连接恢复后继续采样' : '等待首次采样'}</Typography.Text>
          {forward.lastResolveError ? <Alert type="warning" showIcon message="平台结算暂未核实" description="已记录纸上单保留为待结算，连接恢复后继续核对。" /> : null}
          <Space size="large" wrap align="start">
            <Stats stats={forward.baseline} label={ruleNames.BASELINE} forward />
            {forward.strategies.map(stats => <Stats key={stats.rule} stats={stats} label={ruleNames[stats.rule] || stats.rule} forward />)}
          </Space>
          <Table size="small" rowKey="periodStart" columns={forwardColumns} dataSource={forward.recent} scroll={{ x: 1180 }}
            pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'], showTotal: total => `已载入 ${total} 笔前瞻纸上单` }}
            locale={{ emptyText: '尚无通过完整核验的前瞻纸上单' }} />
        </>}
        <Typography.Text type="secondary">只累计启用后的新记录，不导入旧成绩。至少观察30个自然日且每个候选各有200笔结算单，再比较费用、回撤及被过滤的赢家；这是最低观察要求，不保证策略有效，也不自动转为实盘。</Typography.Text>
      </Space>
    </Card>
    <Card title="BTC 旧记录 · 平台结算校正">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Tag>历史PREPARE · 含回填或来源时间不明 · 不计入新前瞻</Tag>
        <Typography.Text type="secondary">保留原Binance估算，用平台最终兑付核对输赢。净额使用当前费率模型，不是历史实付费用，也未计Future额外收费。旧记录缺完整执行快照，不代表真实成交。</Typography.Text>
        {!legacy || error ? <Alert type="info" showIcon message="等待历史记录校正" description={error || '旧记录仍保留在原始账本中，校正后逐笔显示。'} /> : <>
          {!legacy.fresh ? <Alert type="warning" showIcon message="历史同步已过期" description="保留上次已核实结果；下方读取时间对应旧快照，恢复后继续同步。" /> : null}
          {legacy.lastError ? <Alert type="warning" showIcon message="历史校正尚未完成" description="保留已核实结果，未核实的结算或费用显示为待核实。" /> : null}
          <Typography.Text>平台已核实 {legacy.verified} / {legacy.total} 笔 · 与原估算结果差异 {legacy.mismatches} 笔</Typography.Text>
          <Typography.Text type="secondary">原账本读取时间：{time(legacy.fetchedAt)}</Typography.Text>
          <Typography.Text strong>全部旧准备记录</Typography.Text>
          <Space size="large" wrap align="start">
            <Stats stats={legacy.baseline} label="全部PREPARE" />
            {legacy.strategies.map(stats => <Stats key={stats.rule} stats={stats} label={stats.rule} />)}
          </Space>
          <Typography.Text strong>其中准备价60–97¢（仅价格子集，不代表完整入场）</Typography.Text>
          <Space size="large" wrap align="start">
            <Stats stats={legacy.priceEligibleStats.baseline} label="价格合格基线" />
            {legacy.priceEligibleStats.strategies.map(stats => <Stats key={stats.rule} stats={stats} label={stats.rule} />)}
          </Space>
          <Table size="small" rowKey="periodStart" columns={legacyColumns} dataSource={legacy.recent} scroll={{ x: 900 }}
            pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20', '50', '100'], showTotal: total => `共 ${total} 笔旧记录` }}
            locale={{ emptyText: '等待完整旧账本读取及逐笔校正' }} />
        </>}
      </Space>
    </Card>
  </Space>
}
