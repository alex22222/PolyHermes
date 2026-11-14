import { Card, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { FutureBtc5mPaperListEntry, FutureBtc5mPaperRegime, FutureBtc5mPaperRegimeStats } from '../types'

const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const money = (value: number | null) => value == null ? '—' : `${value < 0 ? '-' : '+'}$${Math.abs(value).toFixed(2)}`
const cents = (value: number) => `${value.toFixed(0)}¢`
const price = (value: number | null) => value == null ? '—' : value.toLocaleString('en-US', { maximumFractionDigits: 2 })
const time = (value: number) => new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })

const statsText = (label: string, stats: FutureBtc5mPaperRegimeStats, color?: string) =>
  <Space direction="vertical" size={4}>
    <Typography.Text strong style={color ? { color } : undefined}>{label}</Typography.Text>
    <Typography.Text>影子单 {stats.trades} 笔 · 已结算 {stats.settled} 笔</Typography.Text>
    <Typography.Text>胜率 {percent(stats.winRate)}（赢 {stats.wins} 笔）</Typography.Text>
    <Typography.Text>平均每笔收益率 {percent(stats.roiPerDollar)}</Typography.Text>
    <Typography.Text strong style={color ? { color } : undefined}>累计纸面盈亏 {money(stats.settled > 0 ? stats.totalUsd : null)}</Typography.Text>
  </Space>

export interface FutureBtc5mPaperHistory {
  list: FutureBtc5mPaperListEntry[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  error: string | null
}

const columns: ColumnsType<FutureBtc5mPaperListEntry> = [
  { title: '轮次开始', dataIndex: 'periodStart', width: 170, render: time },
  { title: '方向', dataIndex: 'side', width: 70,
    render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
  { title: '价格', dataIndex: 'priceCents', width: 80, render: cents },
  { title: '1小时趋势', dataIndex: 'trend60Bp', width: 110,
    render: (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}bp` },
  { title: 'G1 合格', dataIndex: 'g1Eligible', width: 90,
    render: (value: boolean) => value ? <Tag color="processing">合格</Tag> : <Tag>过滤</Tag> },
  { title: 'G2 合格', dataIndex: 'g2Eligible', width: 90,
    render: (value: boolean | null | undefined) => value == null ? '—'
      : value ? <Tag color="warning">合格</Tag> : <Tag>过滤</Tag> },
  { title: 'Binance 开→收', width: 170,
    render: (_, record) => record.binanceOpen == null ? '—' : `${price(record.binanceOpen)} → ${price(record.binanceClose)}` },
  { title: '结果', dataIndex: 'win', width: 90,
    render: (win: boolean | null, record) => record.state === 'PENDING' ? <Tag>待结算</Tag>
      : win == null ? <Tag>平局</Tag>
      : <Tag color={win ? 'green' : 'red'}>{win ? '赢' : '亏'}</Tag> },
  { title: '纸面盈亏', dataIndex: 'roi', width: 110,
    render: (roi: number | null, record) => <Typography.Text>{record.state === 'PENDING' ? '—' : money(roi)}</Typography.Text> },
]

// Live paper comparison of regime filters G1/G2 against the unfiltered baseline; it never places orders.
// The history table is fed by the page through /future-btc5m/paper/list so every shadow trade can be browsed.
export default function FutureBtc5mPaperRegimeCard({ paper, history, onHistoryPageChange }: {
  paper: FutureBtc5mPaperRegime | null
  history: FutureBtc5mPaperHistory | null
  onHistoryPageChange: (page: number, pageSize: number) => void
}) {
  if (!paper) {
    return <Card title="趋势过滤器纸上验证 · G1 |trend60|>=15bp + G2 避开5-15bp">
      <Space direction="vertical" size={4}>
        <Tag color="orange">旧版历史PREPARE · 非完整入场 · 未扣费估算</Tag>
        <Typography.Text type="secondary">
          每轮 15m PREPARE 决策会镜像一笔 $1 影子单（决策时价格），按 Binance 15m K线估算结算；只记录不下单，不影响真实交易。真实规则不变。
        </Typography.Text>
        <Typography.Text type="secondary">
          还没有影子单：上一轮 PREPARE 决策出现后自动开始累计（SKIP 轮次不产生影子单）。数据出现后本卡片展示基线与 G1/G2 过滤后的对比和全部影子单记录。
        </Typography.Text>
      </Space>
    </Card>
  }
  return <Card title={`趋势过滤器纸上验证 · ${paper.rule}${paper.ruleG2 ? ` + ${paper.ruleG2}` : ''}`}>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Tag color="orange">旧版历史PREPARE · 含回填 · 非完整入场 · 未扣费估算</Tag>
      <Typography.Text strong>此处保留原始Binance估算用于核对；正式平台结果见“旧记录 · 平台结算校正”，新增策略成绩见“BTC策略前瞻验证”。</Typography.Text>
      <Typography.Text type="secondary">
        每轮 15m PREPARE 决策镜像一笔 $1 影子单（决策时价格），按 Binance 15m K线估算结算；只记录不下单，不影响真实交易。真实规则不变。
        G1 只保留趋势明显的轮次（|1小时趋势| ≥ 15bp）；G2 只避开 5–15bp 的震荡带（太平的 &lt;5bp 照常出手）。
      </Typography.Text>
      <Space size="large" wrap align="start">
        {statsText('基线（全部影子单）', paper.baseline)}
        {statsText('G1 过滤后（仅 |1小时趋势| ≥ 15bp）', paper.filtered, '#237804')}
        {paper.filteredG2 ? statsText('G2 过滤后（避开 5–15bp 震荡带）', paper.filteredG2, '#ad6800') : null}
      </Space>
      <Table rowKey={(record) => `${record.periodStart}`} size="small" columns={columns} scroll={{ x: 990 }}
        dataSource={history?.list ?? []} loading={history == null || history.loading}
        pagination={history == null ? false : {
          current: history.page, pageSize: history.pageSize, total: history.total,
          showSizeChanger: true, pageSizeOptions: ['10', '20', '50', '100'],
          showTotal: (total) => `共 ${total} 笔影子单`,
          onChange: onHistoryPageChange,
        }}
        locale={{ emptyText: history?.error ?? '暂无影子单记录' }} />
      <Typography.Text type="secondary">
        {history?.error ? `影子单记录读取失败：${history.error}` : '全部影子单（含待结算），最新轮次在前'} · 汇总更新于 {time(paper.updatedAt)}
      </Typography.Text>
    </Space>
  </Card>
}
