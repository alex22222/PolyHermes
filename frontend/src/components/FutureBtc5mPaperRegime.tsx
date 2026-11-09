import { Card, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { FutureBtc5mPaperRegime, FutureBtc5mPaperRegimeStats, FutureBtc5mPaperRegimeTrade } from '../types'

const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const money = (value: number | null) => value == null ? '—' : `${value < 0 ? '-' : '+'}$${Math.abs(value).toFixed(2)}`
const cents = (value: number) => `${value.toFixed(0)}¢`
const time = (value: number) => new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })

const statsText = (label: string, stats: FutureBtc5mPaperRegimeStats, color?: string) =>
  <Space direction="vertical" size={4}>
    <Typography.Text strong style={color ? { color } : undefined}>{label}</Typography.Text>
    <Typography.Text>影子单 {stats.trades} 笔 · 已结算 {stats.settled} 笔</Typography.Text>
    <Typography.Text>胜率 {percent(stats.winRate)}（赢 {stats.wins} 笔）</Typography.Text>
    <Typography.Text>平均每笔收益率 {percent(stats.roiPerDollar)}</Typography.Text>
    <Typography.Text strong style={color ? { color } : undefined}>累计纸面盈亏 {money(stats.settled > 0 ? stats.totalUsd : null)}</Typography.Text>
  </Space>

const columns: ColumnsType<FutureBtc5mPaperRegimeTrade> = [
  { title: '轮次开始', dataIndex: 'periodStart', width: 170, render: time },
  { title: '方向', dataIndex: 'side', width: 70,
    render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
  { title: '价格', dataIndex: 'priceCents', width: 80, render: cents },
  { title: '1小时趋势', dataIndex: 'trend60Bp', width: 110,
    render: (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}bp` },
  { title: 'G1 合格', dataIndex: 'g1Eligible', width: 90,
    render: (value: boolean) => value ? <Tag color="processing">合格</Tag> : <Tag>过滤</Tag> },
  { title: '结果', dataIndex: 'win', width: 90,
    render: (win: boolean | null) => win == null ? <Tag>平局/待定</Tag>
      : <Tag color={win ? 'green' : 'red'}>{win ? '赢' : '亏'}</Tag> },
  { title: '纸面盈亏', dataIndex: 'roi', width: 110,
    render: (roi: number | null) => <Typography.Text>{money(roi)}</Typography.Text> },
]

// Live paper comparison of regime filter G1 against the unfiltered baseline; it never places orders.
export default function FutureBtc5mPaperRegimeCard({ paper }: { paper: FutureBtc5mPaperRegime | null }) {
  if (!paper) {
    return <Card title="趋势过滤器纸上验证 · G1 |trend60|>=15bp">
      <Space direction="vertical" size={4}>
        <Typography.Text type="secondary">
          每轮 15m PREPARE 决策会镜像一笔 $1 影子单（决策时价格），按 Binance 15m K线估算结算；只记录不下单，不影响真实交易。真实规则不变。
        </Typography.Text>
        <Typography.Text type="secondary">
          还没有影子单：上一轮 PREPARE 决策出现后自动开始累计（SKIP 轮次不产生影子单）。数据出现后本卡片展示基线与 G1 过滤后的对比。
        </Typography.Text>
      </Space>
    </Card>
  }
  return <Card title={`趋势过滤器纸上验证 · ${paper.rule}`}>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Typography.Text type="secondary">
        每轮 15m PREPARE 决策镜像一笔 $1 影子单（决策时价格），按 Binance 15m K线估算结算；只记录不下单，不影响真实交易。真实规则不变。
      </Typography.Text>
      <Space size="large" wrap align="start">
        {statsText('基线（全部影子单）', paper.baseline)}
        {statsText('G1 过滤后（仅 |1小时趋势| ≥ 15bp）', paper.filtered, '#237804')}
      </Space>
      <Table rowKey={(record) => `${record.periodStart}`} size="small" dataSource={paper.recent} columns={columns}
        pagination={false} scroll={{ x: 720 }} locale={{ emptyText: '暂无已结算的影子单' }} />
      <Typography.Text type="secondary">最近 {paper.recent.length} 笔已结算影子单 · 汇总更新于 {time(paper.updatedAt)}</Typography.Text>
    </Space>
  </Card>
}
