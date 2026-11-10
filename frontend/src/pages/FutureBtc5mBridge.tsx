import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Progress, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { useMediaQuery } from 'react-responsive'
import { apiService } from '../services/api'
import FutureStrategyPerformance from '../components/FutureStrategyPerformance'
import FutureBtc5mPaperRegimeCard, { type FutureBtc5mPaperHistory } from '../components/FutureBtc5mPaperRegime'
import { referenceIsFresh } from '../utils/futureBtc5mPreflight'
import type { FutureBtc5mAssets, FutureBtc5mAssetBuy, FutureBtc5mAssetPosition, FutureBtc5mBridgeStatus, FutureBtc5mFourHour, FutureBtc5mStrategy, FutureBtcStrategyPerformance } from '../types'

// 我的资产 refreshes once a minute; a response stays displayable until the next one is overdue.
const ASSETS_REFRESH_MS = 60_000
const ASSETS_FRESH_MS = 75_000

const formatTime = (value?: number | null): string => {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

const formatValue = (value?: number | null, prefix = ''): string =>
  value == null || !Number.isFinite(value) ? '—' : `${prefix}${value.toLocaleString('zh-CN', { maximumFractionDigits: 6 })}`

const formatMoney = (value?: number | null): string => value == null || !Number.isFinite(value)
  ? '—' : `$${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const formatCents = (value?: number | null): string => value == null || !Number.isFinite(value)
  ? '—' : `${(value * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}¢`

const errorText = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback

// The bridge confirms which strategy runs. 15m is the default since 2026-10-16.
const strategyText: Record<FutureBtc5mStrategy, { label: string, rule: string }> = {
  btc15m_counter_1h: {
    label: '15 分钟盘 · 反 1 小时方向（默认）',
    rule: '每轮第 150–170 秒读取 15 分钟盘按钮数字较大的一方；只有它与同一时刻 1 小时盘的热门方向相反，且 BTC 过去 60 分钟波动不高于 4.16 基点/分钟（R1 高波动过滤）时，才准备 $1 并自动买入；方向相同或波动过高则本轮跳过。',
  },
  btc15m_plus_4h: {
    label: '15 分钟盘反 1 小时 + 周末 4 小时高把握',
    rule: '15 分钟部分同上（含 R1 高波动过滤）。周末 4 小时盘在每刻钟第 5、10 分钟按 Binance 价格模型判断：模型把握 ≥95% 且比 Polymarket 卖价高 ≥3¢ 时，接下来 2 分钟切到 4 小时盘准备 $1 并自动买入，每轮最多一次。',
  },
  btc4h_high_confidence: {
    label: '4 小时盘 · 周末高把握',
    rule: '周末 4 小时盘在每刻钟第 5、10 分钟按 Binance 价格模型判断：模型把握 ≥95% 且比 Polymarket 卖价高 ≥3¢ 时，接下来 2 分钟准备 $1 并自动买入，每轮最多一次。',
  },
  btc5m_favorite: {
    label: '5 分钟盘 · 买热门方向',
    rule: '每轮第 60–80 秒按 Up / Down 按钮数字较高的一侧准备 $1 并自动买入。',
  },
}

// 买点图跟随当前策略：只展示该策略实际交易的市场序列；5 分钟策略已停用，不再展示收益。
const strategyPerformanceSeries: Record<FutureBtc5mStrategy, FutureBtcStrategyPerformance['series'][]> = {
  btc15m_counter_1h: ['15m'],
  btc15m_plus_4h: ['15m', '4h'],
  btc4h_high_confidence: ['4h'],
  btc5m_favorite: [],
}

const fourHourReasons: Record<string, string> = {
  MODEL_BELOW_THRESHOLD: '模型把握不足 95%', EDGE_TOO_SMALL: '比卖价高不足 3¢', MODEL_SIDE_NOT_FAVORITE: '模型方向不是盘口热门',
  ASK_OUT_OF_RANGE: '卖价不在 60–97¢', ASK_UNAVAILABLE: '盘口卖价缺失', NOT_ET_WEEKEND: '非美东周末',
}

// One line for the weekend 4h leg: this round's decision, else its latest checkpoint evaluation.
const fourHourText = (value: FutureBtc5mFourHour): string => {
  const side = (s: string | null | undefined) => s === 'Up' ? '涨' : s === 'Down' ? '跌' : '—'
  const cents = (v: number | null) => v == null ? '—' : `${v}¢`
  if (!value.weekend) return `本轮 ${formatTime(value.periodStart)} 起：非美东周末，不运行`
  if (value.decision) {
    return `本轮已决定买${side(value.decision.side)}（${formatTime(value.decision.checkpointAt)} 起 2 分钟内准备，每轮一次）`
  }
  const last = value.lastEvaluation
  if (!last) return `本轮 ${formatTime(value.periodStart)} 起：尚未到判断时点或数据未就绪`
  const probability = last.side === 'Down' ? 1 - last.pUp : last.pUp
  return `最近第 ${last.minute} 分钟：模型看${side(last.side)} ${(probability * 100).toFixed(1)}% · 卖价 涨 ${cents(last.upAskCents)} / 跌 ${cents(last.downAskCents)} · ${last.reason ? fourHourReasons[last.reason] ?? last.reason : '已决定买入'}`
}

const marketLink = (slug: string) => /^btc-updown-(5m|15m|4h)-\d+$/.test(slug)
  ? <Typography.Link href={`https://future.news/zh/event/${slug}`} target="_blank" rel="noopener noreferrer">{slug}</Typography.Link>
  : <Typography.Text>{slug}</Typography.Text>

const FutureBtc5mBridge: React.FC = () => {
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [runtime, setRuntime] = useState<FutureBtc5mBridgeStatus | null>(null)
  const [statusReceivedAt, setStatusReceivedAt] = useState(0)
  const [clock, setClock] = useState(Date.now)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [controlLoading, setControlLoading] = useState(false)
  const [strategyLoading, setStrategyLoading] = useState(false)
  const [assets, setAssets] = useState<FutureBtc5mAssets | null>(null)
  const [assetsError, setAssetsError] = useState<string | null>(null)
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetsReceivedAt, setAssetsReceivedAt] = useState(0)
  const [buyPagination, setBuyPagination] = useState({ current: 1, pageSize: 20 })
  const [paperHistory, setPaperHistory] = useState<FutureBtc5mPaperHistory | null>(null)
  const mounted = useRef(true)
  const controlPending = useRef(false)
  const statusRequestSeq = useRef(0)
  const assetsRequestSeq = useRef(0)
  const statusInFlight = useRef<number | null>(null)
  const assetsInFlight = useRef<number | null>(null)
  const paperRequestSeq = useRef(0)
  const paperInFlight = useRef<number | null>(null)
  const paperView = useRef({ page: 1, pageSize: 20 })
  const assetsRequestedAt = useRef(0)
  const buyHistorySnapshot = useRef<{ walletAddress: string | null, count: number }>({ walletAddress: null, count: 0 })

  useEffect(() => {
    mounted.current = true
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => {
      window.clearInterval(timer)
      mounted.current = false
      statusRequestSeq.current += 1
      assetsRequestSeq.current += 1
    }
  }, [])

  const fetchAssets = useCallback(async () => {
    if (assetsInFlight.current === assetsRequestSeq.current) return
    const requestSeq = ++assetsRequestSeq.current
    assetsInFlight.current = requestSeq
    assetsRequestedAt.current = Date.now()
    setAssetsLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.assets()
      if (!mounted.current || requestSeq !== assetsRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取钱包资产失败')
      }
      const nextAssets = response.data.data
      const walletAddress = nextAssets.wallet?.walletAddress.toLowerCase() ?? null
      const count = nextAssets.recentBuys?.length ?? 0
      if (walletAddress !== buyHistorySnapshot.current.walletAddress || count < buyHistorySnapshot.current.count) {
        setBuyPagination((prev) => ({ ...prev, current: 1 }))
      }
      buyHistorySnapshot.current = { walletAddress, count }
      const receivedAt = Date.now()
      setAssets(nextAssets)
      setAssetsReceivedAt(receivedAt)
      setAssetsError(null)
      setClock(receivedAt)
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== assetsRequestSeq.current) return
      setAssets(null)
      setAssetsError(errorText(error, '获取钱包资产失败'))
    } finally {
      if (assetsInFlight.current === requestSeq) assetsInFlight.current = null
      if (mounted.current && requestSeq === assetsRequestSeq.current) setAssetsLoading(false)
    }
  }, [])

  const fetchStatus = useCallback(async () => {
    if (controlPending.current || statusInFlight.current === statusRequestSeq.current) return
    const requestSeq = ++statusRequestSeq.current
    statusInFlight.current = requestSeq
    setStatusLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.status()
      if (!mounted.current || requestSeq !== statusRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取 Future Bridge 状态失败')
      }
      const receivedAt = Date.now()
      setRuntime(response.data.data)
      setStatusReceivedAt(receivedAt)
      setClock(receivedAt)
      setStatusError(null)
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== statusRequestSeq.current) return
      setRuntime(null)
      setStatusError(errorText(error, '获取 Future Bridge 状态失败'))
    } finally {
      if (statusInFlight.current === requestSeq) statusInFlight.current = null
      if (mounted.current && requestSeq === statusRequestSeq.current) setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = window.setInterval(fetchStatus, 5000)
    return () => window.clearInterval(interval)
  }, [fetchStatus])

  // Full paginated paper ledger for the regime card; refetch when the ledger grows or settles a trade.
  const fetchPaperList = useCallback(async (page: number, pageSize: number) => {
    paperView.current = { page, pageSize }
    const requestSeq = ++paperRequestSeq.current
    paperInFlight.current = requestSeq
    setPaperHistory((prev) => prev ? { ...prev, loading: true } : null)
    try {
      const response = await apiService.futureBtc5mBridge.paperList({ page, size: pageSize })
      if (!mounted.current || requestSeq !== paperRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取影子单记录失败')
      }
      const data = response.data.data
      setPaperHistory({ list: data.list, total: data.total, page: data.page, pageSize: data.size, loading: false, error: null })
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== paperRequestSeq.current) return
      setPaperHistory((prev) => ({ list: prev?.list ?? [], total: prev?.total ?? 0, page, pageSize,
        loading: false, error: errorText(error, '获取影子单记录失败') }))
    } finally {
      if (paperInFlight.current === requestSeq) paperInFlight.current = null
    }
  }, [])

  const paperLedger = runtime?.paperRegime?.baseline
  const paperLedgerKey = paperLedger ? `${paperLedger.trades}:${paperLedger.settled}` : null
  useEffect(() => {
    if (paperLedgerKey != null) fetchPaperList(paperView.current.page, paperView.current.pageSize)
  }, [fetchPaperList, paperLedgerKey])

  useEffect(() => {
    fetchAssets()
    const interval = window.setInterval(fetchAssets, ASSETS_REFRESH_MS)
    return () => window.clearInterval(interval)
  }, [fetchAssets])

  useEffect(() => {
    const refreshConnection = () => {
      if (document.visibilityState === 'hidden') return
      setClock(Date.now())
      fetchStatus()
      if (Date.now() - assetsRequestedAt.current >= ASSETS_REFRESH_MS) fetchAssets()
    }
    window.addEventListener('focus', refreshConnection)
    window.addEventListener('online', refreshConnection)
    document.addEventListener('visibilitychange', refreshConnection)
    return () => {
      window.removeEventListener('focus', refreshConnection)
      window.removeEventListener('online', refreshConnection)
      document.removeEventListener('visibilitychange', refreshConnection)
    }
  }, [fetchStatus, fetchAssets])

  const handleControl = async (enabled: boolean) => {
    if (controlPending.current) return
    controlPending.current = true
    statusRequestSeq.current += 1
    setStatusLoading(false)
    setControlLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.control({ enabled })
      if (!mounted.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '更新自动准备票据开关失败')
      }
      const receivedAt = Date.now()
      setRuntime(response.data.data)
      setStatusReceivedAt(receivedAt)
      setClock(receivedAt)
      setStatusError(null)
      message.success(enabled ? '自动准备票据已开启，票据准备好后扩展将自动点击买入' : '自动准备票据已关闭，扩展不再自动买入')
    } catch (error: unknown) {
      if (!mounted.current) return
      setRuntime(null)
      setStatusError(`开关状态未知：${errorText(error, '更新失败')}。请刷新核对，或再次点击关闭自动准备票据。`)
      message.error('更新失败，自动准备票据开关状态未知')
    } finally {
      controlPending.current = false
      if (mounted.current) setControlLoading(false)
    }
  }

  const handleStrategy = async (strategy: FutureBtc5mStrategy) => {
    if (controlPending.current) return
    controlPending.current = true
    statusRequestSeq.current += 1
    setStatusLoading(false)
    setStrategyLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.strategy({ strategy })
      if (!mounted.current) return
      if (response.data.code !== 0 || !response.data.data || response.data.data.strategy !== strategy) {
        throw new Error(response.data.msg || '切换策略未获确认')
      }
      const receivedAt = Date.now()
      setRuntime(response.data.data)
      setStatusReceivedAt(receivedAt)
      setClock(receivedAt)
      setStatusError(null)
      message.success(`已切换为：${strategyText[strategy].label}`)
    } catch (error: unknown) {
      if (!mounted.current) return
      setRuntime(null)
      setStatusError(`策略状态未知：${errorText(error, '切换失败')}。请刷新核对当前策略。`)
      message.error('切换失败，当前策略未知')
    } finally {
      controlPending.current = false
      if (mounted.current) setStrategyLoading(false)
    }
  }

  const positionColumns: ColumnsType<FutureBtc5mAssetPosition> = [
    { title: '市场', key: 'market', width: 285, render: (_, record) => <Space direction="vertical" size={0}>
      <Typography.Text>{record.title}</Typography.Text>{marketLink(record.slug)}
    </Space> },
    { title: '方向', dataIndex: 'side', width: 75, render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
    { title: '持有份额', dataIndex: 'quantity', width: 110, render: (value: number) => formatValue(value) },
    { title: '买入均价', dataIndex: 'avgPrice', width: 100, render: formatCents },
    { title: '当前价格', dataIndex: 'currentPrice', width: 100, render: formatCents },
    { title: '当前市值', dataIndex: 'currentValueUsd', width: 110, render: formatMoney },
    { title: '持仓盈亏', dataIndex: 'cashPnlUsd', width: 110, render: (value: number | null) =>
      <Typography.Text type={value == null ? 'secondary' : value < 0 ? 'danger' : 'success'}>{formatMoney(value)}</Typography.Text> },
    { title: '状态', dataIndex: 'redeemable', width: 95, render: (value: boolean) => value ? <Tag>待领取</Tag> : <Tag color="processing">持有中</Tag> }
  ]

  const buyColumns: ColumnsType<FutureBtc5mAssetBuy> = [
    { title: '买入时间', dataIndex: 'boughtAt', width: 175, render: (value: number) => formatTime(value) },
    { title: '市场', key: 'market', width: 285, render: (_, record) => <Space direction="vertical" size={0}>
      <Typography.Text>{record.title}</Typography.Text>{marketLink(record.slug)}
    </Space> },
    { title: '方向', dataIndex: 'side', width: 75, render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
    { title: '买入份额', dataIndex: 'quantity', width: 110, render: (value: number) => formatValue(value) },
    { title: '买入价格', dataIndex: 'price', width: 100, render: formatCents },
    { title: '买入金额', dataIndex: 'amountUsd', width: 110, render: formatMoney },
    { title: '结算结果', dataIndex: 'result', width: 145, render: (result: FutureBtc5mAssetBuy['result'], record) =>
      <Space direction="vertical" size={0}>
        <Tag color={result === 'WIN' ? 'green' : result === 'LOSS' ? 'red' : result === 'PENDING' ? 'processing' : 'default'}>
          {result === 'WIN' ? '赢' : result === 'LOSS' ? '亏' : result === 'PENDING' ? '待结算' : '待确认'}
        </Tag>
        {record.winningSide && <Typography.Text type="secondary">结算方向：{record.winningSide === 'Up' ? '涨' : '跌'}</Typography.Text>}
      </Space> }
  ]

  const wallet = assets?.wallet
  // Assets refresh once a minute: values must have been fresh when they arrived, and that arrival must be recent.
  const assetsAge = clock - assetsReceivedAt
  const assetsRecent = assetsAge >= 0 && assetsAge <= ASSETS_FRESH_MS
  const freshOnArrival = (value: number) => Number.isFinite(value) && assetsReceivedAt / 1000 - value >= 0 && assetsReceivedAt / 1000 - value <= 15
  const walletFresh = Boolean(assetsRecent && wallet?.fresh && [wallet.observedAt, wallet.receivedAt].every(freshOnArrival))
  const marketDataFresh = Boolean(walletFresh && assets?.marketDataObservedAt != null && freshOnArrival(assets.marketDataObservedAt))
  const buyResultCounts = { win: 0, loss: 0, pending: 0, unknown: 0 }
  for (const buy of assets?.recentBuys ?? []) {
    if (buy.result === 'WIN') buyResultCounts.win += 1
    else if (buy.result === 'LOSS') buyResultCounts.loss += 1
    else if (buy.result === 'PENDING') buyResultCounts.pending += 1
    else buyResultCounts.unknown += 1
  }
  const settledBuyCount = buyResultCounts.win + buyResultCounts.loss
  const buyWinPercent = settledBuyCount > 0 ? buyResultCounts.win / settledBuyCount * 100 : null
  const buyWinPercentText = buyWinPercent == null ? '—' : `${buyWinPercent.toFixed(1)}%`
  const buyLossPercentText = settledBuyCount > 0 ? `${(buyResultCounts.loss / settledBuyCount * 100).toFixed(1)}%` : '—'

  const statusStale = Boolean(runtime && (clock < statusReceivedAt || clock - statusReceivedAt > 15000 ||
    !Number.isFinite(runtime.serverTime) || Math.abs(runtime.serverTime - statusReceivedAt / 1000) > 3))
  const referenceFresh = referenceIsFresh(runtime, statusReceivedAt, clock)
  const preparation = runtime?.preparation
  const currentStrategy: FutureBtc5mStrategy | null = runtime
    ? runtime.strategy ?? (runtime.series === '15m' ? 'btc15m_counter_1h' : 'btc5m_favorite') : null
  const actualState = runtime && !statusStale
    ? preparation?.enabled ? '自动准备与自动买入已开启' : '自动准备与自动买入已关闭'
    : '状态未知'
  const performanceSeries: FutureBtcStrategyPerformance['series'][] =
    currentStrategy ? strategyPerformanceSeries[currentStrategy] : ['15m']
  const browserConnected = runtime?.preflight?.browserConnected === true
  // EXECUTOR_NOT_CONNECTED 是协议常驻标记（服务端不执行订单、由扩展点击），不是真实阻断。
  const blockReasonText: Record<string, string> = {
    STOP_FILE_PRESENT: '已手动停止（STOP 文件存在）',
    CONTROL_STATE_WRITE_FAILED: '开关状态写入失败',
    SIGNAL_SOURCE_INVALID: '信号源数据无效',
    SIGNAL_SOURCE_UNAVAILABLE: '信号源不可用',
  }
  const realBlockers = (runtime?.blockReasons ?? [])
    .filter((reason) => reason !== 'EXECUTOR_NOT_CONNECTED')
    .map((reason) => blockReasonText[reason] ?? reason)
  const orderBlockText = !runtime || statusStale ? '—'
    : !runtime.requestedEnabled ? '开关已关闭'
    : [...(browserConnected ? [] : ['浏览器扩展未连接']), ...realBlockers].join('；') || '无'
  const actualOrderText = !runtime || statusStale ? '未知'
    : !runtime.requestedEnabled ? '已关闭'
    : !browserConnected ? '等待浏览器扩展连接'
    : '扩展待机中（票据就绪即自动点击）'

  return <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <div>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>Future BTC 自动策略 Bridge</Typography.Title>
      <Typography.Text type="secondary">按所选策略在 Future 上自动准备 BTC $1 票据，准备好后由浏览器扩展自动点击一次买入。当前策略：{currentStrategy ? strategyText[currentStrategy].label : '未知'}。每 5 秒刷新 Bridge 运行状态，每分钟刷新钱包资产。</Typography.Text>
    </div>

    <Card title="我的资产 · BTC 5/15 分钟" extra={<Space wrap>
      <Button icon={<ReloadOutlined />} loading={statusLoading} onClick={fetchStatus}>刷新状态</Button>
      <Button icon={<ReloadOutlined />} loading={assetsLoading} onClick={fetchAssets}>刷新资产</Button>
    </Space>}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Typography.Text strong>交易策略</Typography.Text>
          <Select value={currentStrategy ?? undefined} placeholder="策略未知" style={{ minWidth: 260 }} loading={strategyLoading}
            disabled={!runtime || statusStale || strategyLoading || controlLoading}
            options={(Object.keys(strategyText) as FutureBtc5mStrategy[]).filter((value) => value !== 'btc5m_favorite')
              .map((value) => ({ value, label: strategyText[value].label }))}
            onChange={(value: FutureBtc5mStrategy) => { if (value !== currentStrategy) handleStrategy(value) }} />
        </Space>
        <Space wrap>
          <Typography.Text strong>自动准备票据开关</Typography.Text>
          <Switch checked={runtime?.requestedEnabled ?? false} loading={controlLoading} disabled={!runtime || statusStale}
            checkedChildren="开启" unCheckedChildren="关闭" onChange={handleControl} />
          <Button danger loading={controlLoading} onClick={() => handleControl(false)}>关闭自动准备票据</Button>
          <Tag color={!runtime || statusStale ? 'default' : preparation?.enabled ? 'processing' : 'default'}>{actualState}</Tag>
          <Typography.Text type="secondary">保存开关：{runtime ? runtime.requestedEnabled ? '开启' : '关闭' : '未知'}</Typography.Text>
        </Space>
        {statusError && <Alert type="error" showIcon message="Bridge 状态未知" description={statusError} />}
        {statusStale && <Alert type="error" showIcon message="运行状态已过期，请刷新核对" description="当前状态时间已失效，开关与准备情况未知；仍可点击关闭自动准备票据。" />}
        {runtime && !runtime.executorReady && <Alert type="info" showIcon message="执行方式：浏览器扩展自动点击买入"
          description={`开启后会前往当前策略的市场。${currentStrategy ? strategyText[currentStrategy].rule : ''}报价缺失或相同则等待。Chainlink 价格仅作参考。票据准备好后，浏览器扩展会自动点击一次 Future 买入（每轮最多一次）；实际成交以 Future 订单为准。`} />}
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="当前策略">{currentStrategy ? strategyText[currentStrategy].label : '未知'}</Descriptions.Item>
          {runtime?.fourHour && <Descriptions.Item label="周末 4 小时判断" span={isMobile ? 1 : 3}>{fourHourText(runtime.fourHour)}</Descriptions.Item>}
          <Descriptions.Item label="Bridge 连接">{runtime ? runtime.online ? '在线' : '离线' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="执行器">{runtime ? '浏览器扩展（自动点击）' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="实际下单">{actualOrderText}</Descriptions.Item>
          <Descriptions.Item label="最终买入">浏览器扩展在票据准备好后自动点击（每轮最多一次）</Descriptions.Item>
          <Descriptions.Item label="行情状态">{runtime?.feedStatus || '—'}</Descriptions.Item>
          <Descriptions.Item label="当前轮次">{formatTime(runtime?.periodStart)}</Descriptions.Item>
          <Descriptions.Item label="服务器更新时间">{formatTime(runtime?.serverTime)}</Descriptions.Item>
          <Descriptions.Item label="下单阻断原因" span={isMobile ? 1 : 3}>{orderBlockText}</Descriptions.Item>
        </Descriptions>
        {runtime?.signal && <Descriptions title="Chainlink 参考采样（不用于选择准备方向）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="市场" span={isMobile ? 1 : 3}>{marketLink(runtime.signal.slug)}</Descriptions.Item>
          <Descriptions.Item label="观察方向">{referenceFresh ? runtime.signal.side || '平价' : '采样已过期'}</Descriptions.Item>
          <Descriptions.Item label="开盘参考价">{formatValue(runtime.signal.open_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="采样价格">{formatValue(runtime.signal.current_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="价格采样时间">{formatTime(runtime.signal.price_observed_at)}</Descriptions.Item>
        </Descriptions>}
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="钱包现金"><Typography.Text strong style={{ fontSize: 24 }}>{formatMoney(walletFresh ? wallet?.cashUsd : null)}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="BTC 5/15 分钟持仓市值"><Typography.Text strong style={{ fontSize: 24 }}>{formatMoney(marketDataFresh ? assets?.positionsValueUsd : null)}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="数据状态"><Tag color={marketDataFresh && assets?.dataStatus === 'READY' ? 'success' : 'warning'}>
            {!assets ? assetsLoading ? '读取中' : '未连接' : !wallet ? '等待钱包' : !walletFresh ? '钱包数据已过期' :
              assets.dataStatus === 'PARTIAL' ? '部分数据不可用' : !marketDataFresh ? '持仓等待更新' : '已更新'}</Tag></Descriptions.Item>
          <Descriptions.Item label="当前钱包" span={isMobile ? 1 : 3}>{wallet
            ? <Typography.Link href={`https://future.news/zh/address/${wallet.walletAddress}`} target="_blank" rel="noopener noreferrer" style={{ wordBreak: 'break-all' }}>{wallet.walletAddress}</Typography.Link>
            : '等待同步'}</Descriptions.Item>
          <Descriptions.Item label="现金采样时间">{formatTime(wallet?.observedAt)}</Descriptions.Item>
          <Descriptions.Item label="持仓与买入更新时间">{formatTime(assets?.marketDataObservedAt)}</Descriptions.Item>
        </Descriptions>
        <Typography.Text type="secondary">每 5 秒自动刷新。现金取自当前 Future 登录钱包的页面显示；持仓与买入历史按同一地址查询 Polymarket，可能有索引延迟。市值包含待领取持仓，不计入现金。</Typography.Text>
        {assetsError && <Alert type="error" showIcon message="钱包资产暂不可用" description={assetsError} />}
        {assets && (assets.reasons.length > 0 || !walletFresh || !marketDataFresh) && <Alert type="warning" showIcon message="资产数据等待同步"
          description={assets.reasons.join('；') || (!walletFresh ? 'Future 钱包采样已过期，请保持当前市场页面打开。' : '持仓数据已过期，正在重新读取。')} />}
        <Typography.Title level={5} style={{ margin: 0 }}>当前买入资产</Typography.Title>
        {marketDataFresh && assets?.positions != null
          ? <Table rowKey="asset" size="small" dataSource={assets.positions} columns={positionColumns} pagination={false} scroll={{ x: 1085 }}
            locale={{ emptyText: '当前暂无 BTC 5/15 分钟持仓' }} />
          : <Typography.Text type="secondary">{assetsLoading ? '正在读取持仓…' : '持仓暂未核实'}</Typography.Text>}
        {marketDataFresh && performanceSeries.length > 0 && <FutureStrategyPerformance
          performance={assets?.performance?.filter((point) => performanceSeries.includes(point.series))}
          series={performanceSeries} />}
        <Typography.Title level={5} style={{ margin: 0 }}>全部买入记录</Typography.Title>
        <Typography.Text type="secondary">赢 / 亏按市场最终结算方向标注，表示买入方向是否命中；不代表已领取，也不表示包含提前卖出和手续费的实际净盈亏。</Typography.Text>
        {marketDataFresh && assets?.recentBuys != null
          ? <>
            <Typography.Text type="secondary">已加载 {assets.recentBuys.length} 笔 · {assets.buyHistoryComplete === true ? '历史记录已完整加载' : '历史记录未完整加载'}</Typography.Text>
            {assets.buyHistoryComplete !== true && <Alert type="warning" showIcon message="买入历史尚未完整核实"
              description="当前仅展示已加载记录，不能视为全部买入；请等待历史数据完整同步后核对。" />}
            <div style={{ width: '100%', boxSizing: 'border-box', padding: isMobile ? 16 : 20, background: '#fafafa', borderRadius: 8 }}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>赢亏比例</Typography.Title>
              <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: 'center', gap: isMobile ? 20 : 32 }}>
                <div role="img" aria-label={`赢亏比例：赢 ${buyResultCounts.win} 笔，亏 ${buyResultCounts.loss} 笔，${buyWinPercent == null ? '暂无已结算记录，胜率未知' : `已结算胜率 ${buyWinPercentText}`}`}>
                  <Progress type="circle" size={160} percent={buyWinPercent ?? 0} status="normal" strokeWidth={10}
                    strokeColor="#52c41a" trailColor={settledBuyCount > 0 ? '#ff4d4f' : '#f0f0f0'} strokeLinecap="butt"
                    format={() => <>
                      <Typography.Text strong style={{ display: 'block', fontSize: 28 }}>{buyWinPercentText}</Typography.Text>
                      <Typography.Text style={{ fontSize: 12, color: '#595959' }}>{settledBuyCount > 0 ? '已结算胜率' : '暂无已结算记录'}</Typography.Text>
                    </>} />
                </div>
                <Space direction="vertical" size={12} style={{ width: isMobile ? '100%' : undefined }}>
                  <Typography.Text strong style={{ color: '#237804' }}>赢 {buyResultCounts.win} 笔 · {buyWinPercentText}</Typography.Text>
                  <Typography.Text strong style={{ color: '#cf1322' }}>亏 {buyResultCounts.loss} 笔 · {buyLossPercentText}</Typography.Text>
                  <Typography.Text style={{ color: '#595959' }}>待结算 {buyResultCounts.pending} 笔</Typography.Text>
                  <Typography.Text style={{ color: '#595959' }}>待确认 {buyResultCounts.unknown} 笔</Typography.Text>
                </Space>
              </div>
              <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0, color: '#595959' }}>
                已结算 {settledBuyCount} 笔。按已加载的全部买入笔数统计，同一轮多笔分别计数；待结算和待确认不计入胜率。
              </Typography.Paragraph>
              {assets.buyHistoryComplete !== true && <Typography.Text style={{ color: '#874d00' }}>仅统计已加载记录，完整历史同步后比例可能变化。</Typography.Text>}
            </div>
            <Table rowKey={(record, index) => `${record.id}:${index}`} size="small" dataSource={assets.recentBuys} columns={buyColumns} scroll={{ x: 1000 }}
              pagination={{ ...buyPagination, total: assets.recentBuys.length, showSizeChanger: true,
                pageSizeOptions: ['10', '20', '50', '100'], showTotal: (total) => `已加载 ${total} 笔`,
                onChange: (current, pageSize) => setBuyPagination({ current, pageSize }) }}
              locale={{ emptyText: assets.buyHistoryComplete === true ? '暂无 BTC 5/15 分钟买入记录' : '当前尚未加载 BTC 5/15 分钟买入记录' }} />
          </>
          : <Typography.Text type="secondary">{assetsLoading ? '正在读取买入记录…' : '买入历史暂未核实'}</Typography.Text>}
      </Space>
    </Card>

    <FutureBtc5mPaperRegimeCard paper={runtime?.paperRegime ?? null} history={paperHistory}
      onHistoryPageChange={fetchPaperList} />

  </Space>
}

export default FutureBtc5mBridge
