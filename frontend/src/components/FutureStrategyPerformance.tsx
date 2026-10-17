import { Card, Empty, Space, Tag, Typography } from 'antd'
import type { FutureBtcStrategyPerformance } from '../types'

const money = (value: number | null) => value == null ? '—' : `${value < 0 ? '-' : value > 0 ? '+' : ''}$${Math.abs(value).toFixed(6)}`
const date = (at: number) => new Date(at * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })

export const PerformanceCurve = ({ data }: { data: FutureBtcStrategyPerformance }) => {
  if (!data.historyComplete || data.curve.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={data.historyComplete ? '暂无已核实的结算收益曲线' : '历史同步完成后展示累计收益曲线'} />
  const first = data.curve[0]
  const points = [{ at: first.at - (data.series === '5m' ? 300 : 900), netPnlUsd: 0 }, ...data.curve]
  const min = Math.min(0, ...points.map(p => p.netPnlUsd))
  const max = Math.max(0, ...points.map(p => p.netPnlUsd))
  const range = max - min || 1
  const x = (at: number) => 60 + (at - points[0].at) / (points[points.length - 1].at - points[0].at) * 510
  const y = (value: number) => 35 + (max - value) / range * 130
  return <svg role="img" aria-label={`${data.series} 累计扣费净盈亏曲线，${data.curve.length} 个已结算仓位，最终 ${money(data.netPnlUsd)}`}
    viewBox="0 0 600 210" style={{ width: '100%', display: 'block' }}>
    <title>累计扣费后净盈亏，按市场结束时间排列，单位美元</title>
    {[max, min].filter((value, i, all) => all.indexOf(value) === i).map(value => <g key={value}>
      <line x1={60} x2={570} y1={y(value)} y2={y(value)} stroke="#e8e8e8" />
      <text x={52} y={y(value) + 4} textAnchor="end" fontSize={12} fill="#595959">{value.toFixed(2)}</text>
    </g>)}
    <line x1={60} x2={570} y1={y(0)} y2={y(0)} stroke="#bfbfbf" strokeDasharray="4 4" />
    <polyline fill="none" stroke="#1677ff" strokeWidth={2} points={points.map(p => `${x(p.at)},${y(p.netPnlUsd)}`).join(' ')} />
    {data.curve.map((p, i) => <circle key={`${p.at}:${i}`} cx={x(p.at)} cy={y(p.netPnlUsd)} r={3} fill="#1677ff">
      <title>{date(p.at)} · {money(p.netPnlUsd)}</title>
    </circle>)}
    <text x={60} y={193} fontSize={12} fill="#595959">{date(points[0].at)}</text>
    <text x={570} y={193} textAnchor="end" fontSize={12} fill="#595959">{date(points[points.length - 1].at)}</text>
  </svg>
}

const FutureStrategyPerformance = ({ performance }: { performance?: FutureBtcStrategyPerformance[] | null }) =>
  <Space direction="vertical" style={{ width: '100%' }}>
    <Typography.Title level={5} style={{ margin: 0 }}>策略已结算表现</Typography.Title>
    <Typography.Text type="secondary">每 5 秒自动刷新。按当前钱包的 BTC 5m / 15m 市场归类，包含同周期手动买入；同一市场同一方向的多次成交合并为一个仓位。净盈亏为实际卖出及兑付回款减含费买入成本，手续费不重复扣除。</Typography.Text>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))', gap: 16 }}>
      {(['5m', '15m'] as const).map(series => {
        const data = performance?.find(p => p.series === series)
        const ready = data?.historyComplete === true
        return <Card key={series} size="small" title={series === '5m' ? '5 分钟 · 买热门方向' : '15 分钟 · 反 1 小时方向'}>
          {data ? <Space direction="vertical" style={{ width: '100%' }}>
            {!ready && <Tag color="warning">历史同步中，累计统计待核实</Tag>}
            <Space wrap size="large">
              <div><Typography.Text type="secondary">已结算胜率</Typography.Text>
                <Typography.Title level={3} style={{ margin: 0 }}>{ready && data.winRatePercent != null ? `${data.winRatePercent.toFixed(2)}%` : '—'}</Typography.Title></div>
              <div><Typography.Text type="secondary">扣费后净盈亏（USDC）</Typography.Text>
                <Typography.Title level={3} style={{ margin: 0, color: data.netPnlUsd == null ? undefined : data.netPnlUsd < 0 ? '#cf1322' : '#237804' }}>{money(ready ? data.netPnlUsd : null)}</Typography.Title></div>
            </Space>
            <Typography.Text>已结算 {data.settledCount} 个 · 赢 {data.wins} · 亏 {data.losses}</Typography.Text>
            <Typography.Text type="secondary">待结算 / 待领取 / 待核实 {data.excludedCount} 个，不计入上述指标</Typography.Text>
            <Typography.Text type="secondary">按实际总成本计算的收益率：{ready && data.returnPercent != null ? `${data.returnPercent.toFixed(2)}%` : '—'}</Typography.Text>
            <PerformanceCurve data={data} />
            <Typography.Text type="secondary">累计扣费净盈亏 · 按市场结束时间累计{data.firstBoughtAt == null ? '' : ` · 首笔 ${date(data.firstBoughtAt)}`}</Typography.Text>
          </Space> : <Typography.Text type="secondary">等待完整成交及结算数据…</Typography.Text>}
        </Card>
      })}
    </div>
    <Typography.Text type="secondary">仅统计最终结算已确认且回款可核对的仓位；已结算归零的输单计入亏损。未结算、赢家尚未兑付及流水不完整的记录不计入；胜率表示买入方向命中最终结算方向。</Typography.Text>
  </Space>

export default FutureStrategyPerformance
