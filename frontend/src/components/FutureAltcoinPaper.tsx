import { useEffect, useState } from 'react'
import { Alert, Card, Space, Table, Tag, Typography } from 'antd'
import { apiService } from '../services/api'
import type { PaperObserverStatus } from '../types/futurePaperObserver'

const pct = (v: number | null) => v == null ? '—' : `${(v * 100).toFixed(2)}%`
const money = (v: number | null) => v == null ? '—' : `${v < 0 ? '-' : '+'}$${Math.abs(v).toFixed(4)}`
const time = (v: number) => new Date(v * 1000).toLocaleString('zh-CN', { hour12: false })
const reasons: Record<string, string> = {
  WAITING_ENTRY_WINDOW: '等待本轮入场窗口', ENTRY_WINDOW_CLOSED: '本轮入场窗口已结束',
  R1_HIGH_VOLATILITY: 'R1 波动超过门槛，本轮跳过', SAME_AS_1H: '与1小时同向，本轮跳过',
  PAPER_RECORDED: '已记录影子单', FILTERED_BY_REQUESTED_RULES: '已记录基线，本轮被所选规则过滤',
  TIED_QUOTES: '报价相同，继续等待', PRICE_GATE: '价格未通过门槛', BOOK_STALE: '盘口已过期，继续等待',
}

export function AltcoinPaperView({ data, error }: { data: PaperObserverStatus | null, error: string | null }) {
  return <Card title="新增币种纸上验证 · ETH G1 / G2 · SOL G1">
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Tag color="blue">仅纸上观察 · 每笔模拟本金 $1</Tag>
      <Typography.Text type="secondary">保留 R1、反同币1小时、150–170秒入场窗口、60–97¢及±5¢价格门槛。从启用后累计，不导入历史回测盈亏。</Typography.Text>
      <Typography.Text type="secondary">报价及模拟深度取公开 CLOB；Future 页面与盘口3¢核对未覆盖。按平台最终兑付结果计算市场手续费后的纸面盈亏，未计未核实的 Future 额外收费。</Typography.Text>
      {error || !data?.fresh ? <Alert type="warning" showIcon message="纸上采样状态待核实"
        description={error || '等待独立采集器的新鲜报告；尚无数据时不会显示零收益。'} /> : <>
        <Typography.Text type="secondary">前瞻观察起点：{time(data.startedAt)} · 采集更新：{data.heartbeat == null ? '—' : time(data.heartbeat)}</Typography.Text>
        {data.assets.map(asset => <Card key={asset.asset} size="small" title={`${asset.asset} · 15分钟反1小时`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text>基线 {asset.baseline.trades} 笔 · 已结算 {asset.baseline.settled} 笔（赢 {asset.baseline.wins} / 亏 {asset.baseline.losses}）</Typography.Text>
            <Typography.Text type="secondary">{asset.latest ? reasons[asset.latest.reason] || '行情暂不可用，本轮等待或跳过' : '等待首次采样'}</Typography.Text>
            <Space wrap align="start" size="large">{asset.strategies.map(strategy => <Space key={strategy.rule} direction="vertical" size={4}>
              <Typography.Text strong>{asset.asset} {strategy.rule}</Typography.Text>
              <Typography.Text>影子单 {strategy.trades} · 待结算 {strategy.pending} · 已结算 {strategy.settled}</Typography.Text>
              <Typography.Text>胜率 {pct(strategy.winRate)} · 纸面净盈亏 {money(strategy.netPnlUsd)}</Typography.Text>
              <Typography.Text>单位本金收益 {pct(strategy.roiPerDollar)}</Typography.Text>
              <Typography.Text>过滤原亏单 {strategy.filteredLosses ?? 0} / {asset.baseline.losses} · 同时过滤赢家 {strategy.filteredWins ?? 0}</Typography.Text>
            </Space>)}</Space>
            <Table size="small" rowKey="periodStart" dataSource={asset.recent} scroll={{ x: asset.strategies.length > 1 ? 710 : 620 }}
              pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20'], showTotal: total => `最近 ${total} 笔影子单` }}
              locale={{ emptyText: '尚无前瞻影子单，等待符合条件的轮次' }} columns={[
                { title: '轮次开始', dataIndex: 'periodStart', width: 170, render: time },
                { title: '方向', dataIndex: 'side', width: 70,
                  render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
                { title: '模拟均价', dataIndex: 'priceCents', width: 90, render: (v: number) => `${v.toFixed(0)}¢` },
                ...asset.strategies.map(strategy => ({ title: `${strategy.rule} 合格`, key: strategy.rule, dataIndex: 'rules', width: 90,
                  render: (rules: string[]) => rules.includes(strategy.rule)
                    ? <Tag color={strategy.rule === 'G1' ? 'processing' : 'warning'}>合格</Tag> : <Tag>过滤</Tag> })),
                { title: '平台结果', dataIndex: 'win', width: 90,
                  render: (v: boolean | null) => v == null ? <Tag>待核实</Tag> : <Tag color={v ? 'green' : 'red'}>{v ? '赢' : '亏'}</Tag> },
                { title: '纸面盈亏', dataIndex: 'netPnlUsd', width: 110,
                  render: (v: number | null) => <Typography.Text>{v == null ? '—' : `${v < 0 ? '-' : '+'}$${Math.abs(v).toFixed(2)}`}</Typography.Text> },
              ]} />
          </Space>
        </Card>)}
      </>}
    </Space>
  </Card>
}

export default function FutureAltcoinPaper() {
  const [data, setData] = useState<PaperObserverStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    let pending = false
    const refresh = async () => {
      if (pending) return
      pending = true
      try {
        const response = await apiService.futureBtc5mBridge.observerStatus()
        if (!active) return
        if (response.data.code !== 0 || !response.data.data) throw new Error(response.data.msg || '纸上采样暂不可用')
        setData(response.data.data)
        setError(null)
      } catch (e) {
        if (active) { setData(null); setError(e instanceof Error ? e.message : '纸上采样暂不可用') }
      } finally {
        pending = false
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 10000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  return <AltcoinPaperView data={data} error={error} />
}
